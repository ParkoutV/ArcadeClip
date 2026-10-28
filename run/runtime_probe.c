/* Bounded, hidden probes for installer PATH candidates. Never invokes a shell. */
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <wchar.h>
#include <stdio.h>

static int run(const wchar_t *exe, const wchar_t *args) {
    wchar_t command[32768];
    if (swprintf(command, 32768, L"\"%ls\" %ls", exe, args) < 0) return 1;
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    startup.cb = sizeof(startup);
    HANDLE job = CreateJobObjectW(NULL, NULL);
    if (!job) return 1;
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits = {0};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation, &limits, sizeof(limits))) {
        CloseHandle(job); return 1;
    }
    if (!CreateProcessW(exe, command, NULL, NULL, FALSE, CREATE_NO_WINDOW | CREATE_SUSPENDED,
                        NULL, NULL, &startup, &process)) { CloseHandle(job); return 1; }
    if (!AssignProcessToJobObject(job, process.hProcess)) {
        TerminateProcess(process.hProcess, 1);
        CloseHandle(process.hThread); CloseHandle(process.hProcess); CloseHandle(job); return 1;
    }
    ResumeThread(process.hThread);
    DWORD code = 1;
    if (WaitForSingleObject(process.hProcess, 15000) == WAIT_OBJECT_0)
        GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(job);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return (int)code;
}

int wmain(int argc, wchar_t **argv) {
    if (argc < 3) return 1;
    if (!wcscmp(argv[1], L"python") && argc == 4) {
        const wchar_t *platform;
        if (!wcscmp(argv[3], L"arm64")) platform = L"win-arm64";
        else if (!wcscmp(argv[3], L"amd64")) platform = L"win-amd64";
        else return 1;
        wchar_t args[2048];
        swprintf(args, 2048, L"-I -S -c \"import sys,sysconfig;sys.exit(not (sys.implementation.name == 'cpython' and sys.version_info[:2] == (3,13) and sysconfig.get_platform() == '%ls' and not sysconfig.get_config_var('Py_GIL_DISABLED')))\"", platform);
        return run(argv[2], args);
    }
    if (!wcscmp(argv[1], L"ffmpeg"))
        return run(argv[2], L"-nostdin -v error -f lavfi -i testsrc2=size=32x32:rate=1 -f lavfi -i anullsrc -t 0.1 -c:v libx264 -c:a aac -f null -");
    if (!wcscmp(argv[1], L"ffprobe")) return run(argv[2], L"-version");
    return 1;
}
