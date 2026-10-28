/* Portable GUI launcher. The bundled interpreter owns subprocess/multiprocessing. */
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <wchar.h>

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR ignored, int show) {
    wchar_t root[32768], python[32768], command[32768];
    DWORD length = GetModuleFileNameW(NULL, root, 32768);
    if (!length || length >= 32768) return 1;
    wchar_t *slash = wcsrchr(root, L'\\');
    if (!slash) return 1;
    *slash = 0;
    const wchar_t *tail = GetCommandLineW();
    if (*tail == L'"') { tail++; while (*tail && *tail != L'"') tail++; if (*tail) tail++; }
    else { while (*tail && *tail != L' ' && *tail != L'\t') tail++; }
    if (swprintf(python, 32768, L"%ls\\runtime\\python.exe", root) < 0 ||
        swprintf(command, 32768, L"\"%ls\" -X utf8 \"%ls\\start.py\" %ls", python, root, tail) < 0) return 1;
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    startup.cb = sizeof(startup);
    if (!CreateProcessW(python, command, NULL, NULL, FALSE, CREATE_NO_WINDOW,
                        NULL, NULL, &startup, &process)) {
        MessageBoxW(NULL, L"Cannot start bundled Python. Keep the entire application folder together.",
                    L"ArcadeClip", MB_OK | MB_ICONERROR);
        return 1;
    }
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return (int)code;
}
