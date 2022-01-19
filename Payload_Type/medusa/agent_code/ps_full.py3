    def ps_full(self, task_id):
        import sys, os.path, ctypes, ctypes.wintypes
        from ctypes import create_unicode_buffer, GetLastError

        def _check_bool(result, func, args):
            if not result:
                raise ctypes.WinError(ctypes.get_last_error())
            return args

        PULONG = ctypes.POINTER(ctypes.wintypes.ULONG)
        ULONG_PTR = ctypes.wintypes.LPVOID
        SIZE_T = ctypes.c_size_t
        NTSTATUS = ctypes.wintypes.LONG
        PVOID = ctypes.wintypes.LPVOID
        PROCESSINFOCLASS = ctypes.wintypes.ULONG

        Psapi = ctypes.WinDLL('Psapi.dll')
        EnumProcesses = Psapi.EnumProcesses
        EnumProcesses.restype = ctypes.wintypes.BOOL

        Kernel32 = ctypes.WinDLL('kernel32.dll')
        OpenProcess = Kernel32.OpenProcess
        OpenProcess.restype = ctypes.wintypes.HANDLE
        CloseHandle = Kernel32.CloseHandle
        CloseHandle.errcheck = _check_bool
        IsWow64Process = Kernel32.IsWow64Process

        GetCurrentProcess = Kernel32.GetCurrentProcess
        GetCurrentProcess.restype = ctypes.wintypes.HANDLE
        GetCurrentProcess.argtypes = ()

        ReadProcessMemory = Kernel32.ReadProcessMemory
        ReadProcessMemory.errcheck = _check_bool
        ReadProcessMemory.argtypes = (
            ctypes.wintypes.HANDLE, 
            ctypes.wintypes.LPCVOID,
            ctypes.wintypes.LPVOID, 
            SIZE_T,           
            ctypes.POINTER(SIZE_T))

        PROCESS_VM_READ           = 0x0010
        PROCESS_QUERY_INFORMATION = 0x0400

        MAX_PATH = 260
        PROCESS_QUERY_INFORMATION = 0x0400

        ProcessBasicInformation   = 0
        ProcessDebugPort          = 7
        ProcessWow64Information   = 26
        ProcessImageFileName      = 27
        ProcessBreakOnTermination = 29

        STATUS_UNSUCCESSFUL         = NTSTATUS(0xC0000001)
        STATUS_INFO_LENGTH_MISMATCH = NTSTATUS(0xC0000004).value
        STATUS_INVALID_HANDLE       = NTSTATUS(0xC0000008).value
        STATUS_OBJECT_TYPE_MISMATCH = NTSTATUS(0xC0000024).value


        class RemotePointer(ctypes._Pointer):
            def __getitem__(self, key):
                size = None
                if not isinstance(key, tuple):
                    raise KeyError('must be (index, handle[, size])')
                if len(key) > 2:
                    index, handle, size = key
                else:
                    index, handle = key
                if isinstance(index, slice):
                    raise TypeError('slicing is not supported')
                dtype = self._type_
                offset = ctypes.sizeof(dtype) * index
                address = PVOID.from_buffer(self).value + offset
                simple = issubclass(dtype, ctypes._SimpleCData)
                if simple and size is not None:
                    if dtype._type_ == ctypes.wintypes.WCHAR._type_:
                        buf = (ctypes.wintypes.WCHAR * (size // 2))()
                    else: buf = (ctypes.c_char * size)()
                else: buf = dtype()
                nread = SIZE_T()
                Kernel32.ReadProcessMemory(handle, address, ctypes.byref(buf), \
                        ctypes.sizeof(buf), ctypes.byref(nread))
                if simple: return buf.value
                return buf

        _remote_pointer_cache = {}
        def RPOINTER(dtype):
            if dtype in _remote_pointer_cache: return _remote_pointer_cache[dtype]
            name = 'RP_%s' % dtype.__name__
            ptype = type(name, (RemotePointer,), {'_type_': dtype})
            _remote_pointer_cache[dtype] = ptype
            return ptype

        RPWSTR = RPOINTER(ctypes.wintypes.WCHAR)

        class UNICODE_STRING(ctypes.Structure):
            _fields_ = (('Length',        ctypes.wintypes.USHORT),
                        ('MaximumLength', ctypes.wintypes.USHORT),
                        ('Buffer',        RPWSTR))

        class LIST_ENTRY(ctypes.Structure):
            pass

        RPLIST_ENTRY = RPOINTER(LIST_ENTRY)

        LIST_ENTRY._fields_ = (('Flink', RPLIST_ENTRY),
                            ('Blink', RPLIST_ENTRY))

        class PEB_LDR_DATA(ctypes.Structure):
            _fields_ = (('Reserved1',               ctypes.wintypes.BYTE * 8),
                        ('Reserved2',               PVOID * 3),
                        ('InMemoryOrderModuleList', LIST_ENTRY))

        RPPEB_LDR_DATA = RPOINTER(PEB_LDR_DATA)

        class RTL_USER_PROCESS_PARAMETERS(ctypes.Structure):
            _fields_ = (('Reserved1',     ctypes.wintypes.BYTE * 16),
                        ('Reserved2',     PVOID * 10),
                        ('ImagePathName', UNICODE_STRING),
                        ('CommandLine',   UNICODE_STRING))

        RPRTL_USER_PROCESS_PARAMETERS = RPOINTER(RTL_USER_PROCESS_PARAMETERS)
        PPS_POST_PROCESS_INIT_ROUTINE = PVOID

        class PEB(ctypes.Structure):
            _fields_ = (('Reserved1',              ctypes.wintypes.BYTE * 2),
                        ('BeingDebugged',          ctypes.wintypes.BYTE),
                        ('Reserved2',              ctypes.wintypes.BYTE * 1),
                        ('Reserved3',              PVOID * 2),
                        ('Ldr',                    RPPEB_LDR_DATA),
                        ('ProcessParameters',      RPRTL_USER_PROCESS_PARAMETERS),
                        ('Reserved4',              ctypes.wintypes.BYTE * 104),
                        ('Reserved5',              PVOID * 52),
                        ('PostProcessInitRoutine', PPS_POST_PROCESS_INIT_ROUTINE),
                        ('Reserved6',              ctypes.wintypes.BYTE * 128),
                        ('Reserved7',              PVOID * 1),
                        ('SessionId',              ctypes.wintypes.ULONG))

        RPPEB = RPOINTER(PEB)

        class PROCESS_BASIC_INFORMATION(ctypes.Structure):
            _fields_ = (('Reserved1',       PVOID),
                        ('PebBaseAddress',  RPPEB),
                        ('Reserved2',       PVOID * 2),
                        ('UniqueProcessId', ULONG_PTR),
                        ('InheritedFromUniqueProcessId',       ULONG_PTR))

        def NtError(status):
            import sys
            descr = 'NTSTATUS(%#08x) ' % (status % 2**32,)
            if status & 0xC0000000 == 0xC0000000:
                descr += '[Error]'
            elif status & 0x80000000 == 0x80000000:
                descr += '[Warning]'
            elif status & 0x40000000 == 0x40000000:
                descr += '[Information]'
            else:
                descr += '[Success]'
            if sys.version_info[:2] < (3, 3):
                return WindowsError(status, descr)
            return OSError(None, descr, None, status)

        ntdll = ctypes.WinDLL('ntdll.dll')
        NtQueryInformationProcess = ntdll.NtQueryInformationProcess
        NtQueryInformationProcess.restype = NTSTATUS
        NtQueryInformationProcess.argtypes = (
            ctypes.wintypes.HANDLE,
            PROCESSINFOCLASS, 
            PVOID,            
            ctypes.wintypes.ULONG,
            PULONG)        

        class ProcessInformation(object):
            _close_handle = False
            _closed = False
            _module_names = None

            def __init__(self, process_id=None, handle=None):
                if process_id is None and handle is None:
                    handle = GetCurrentProcess()
                elif handle is None:
                    handle = OpenProcess(PROCESS_VM_READ | 
                                            PROCESS_QUERY_INFORMATION,
                                                False, process_id)
                    self._close_handle = True
                self._handle = handle
                if not self._query_info() or (process_id is not None \
                    and self._process_id != process_id):
                    return

            def __del__(self, CloseHandle=CloseHandle):
                if self._close_handle and not self._closed:
                    try:
                        CloseHandle(self._handle)
                    except WindowsError as e: pass
                    self._closed = True

            def _query_info(self):
                info = PROCESS_BASIC_INFORMATION()
                handle = self._handle
                status = NtQueryInformationProcess(handle, ProcessBasicInformation,
                            ctypes.byref(info), ctypes.sizeof(info), None)
                if status < 0:
                    return False

                self._process_id = info.UniqueProcessId
                self._parent_process_id = info.InheritedFromUniqueProcessId
                self._peb = peb = info.PebBaseAddress[0, handle]
                self._params = peb.ProcessParameters[0, handle]

                Is64Bit = ctypes.c_int32()
                IsWow64Process(handle, ctypes.byref(Is64Bit))
                self._arch = "x86" if Is64Bit.value else "x64"

            @property
            def process_id(self):
                return self._process_id

            @property
            def session_id(self):
                return self._peb.SessionId

            @property
            def image_path(self):
                ustr = self._params.ImagePathName
                return ustr.Buffer[0, self._handle, ustr.Length]

            @property
            def command_line(self):
                ustr = self._params.CommandLine
                buf = ustr.Buffer[0, self._handle, ustr.Length]
                return buf

        processes = []

        count = 32
        while True:
            ProcessIds = (ctypes.wintypes.DWORD*count)()
            cb = ctypes.sizeof(ProcessIds)
            BytesReturned = ctypes.wintypes.DWORD()
            if EnumProcesses(ctypes.byref(ProcessIds), cb, ctypes.byref(BytesReturned)):
                if BytesReturned.value<cb:
                    break
                else:
                    count *= 2
            else:
                sys.exit("Call to EnumProcesses failed")

        for index in range(int(BytesReturned.value / ctypes.sizeof(ctypes.wintypes.DWORD))):
            process = {}
            process["process_id"] = ProcessId = ProcessIds[index]
            if ProcessId == 0: continue

            try:
                pi = ProcessInformation(ProcessId)
                process["name"] = os.path.basename(pi.image_path)
                process["architecture"] = str(pi._arch)
                process["bin_path"] = pi.image_path
                process["integrity_level"] = pi.session_id
                process["parent_process_id"] = pi._parent_process_id
                process["command_line"] = pi.command_line
            except:
                pass
            processes.append(process)

        task = [task for task in self.taskings if task["task_id"] == task_id]
        task[0]["processes"] = processes
        return { "processes": processes }
