"""Protected Windows folders; ordinary-user privacy, not an administrator sandbox."""
from __future__ import annotations

import ctypes as C
from functools import lru_cache
import os
from pathlib import Path
import uuid

from state_io import StateError

DWORD = C.c_uint32
WORD = C.c_uint16
PTR = C.c_void_p
FULL_ACCESS = 0x1F01FF
SYSTEM = "S-1-5-18"
ADMINISTRATORS = "S-1-5-32-544"


class SecurityAttributes(C.Structure):
    _fields_ = [("length", DWORD), ("descriptor", PTR), ("inherit", C.c_int)]


class ACL(C.Structure):
    _fields_ = [("revision", C.c_uint8), ("reserved", C.c_uint8),
                ("size", WORD), ("count", WORD), ("reserved2", WORD)]


def acl_issue(owner: str, current_user: str, protected: bool, grants: dict[str, int]) -> str | None:
    if owner != current_user:
        return "The private folder is not owned by the current Windows user."
    if not protected:
        return "The private folder inherits access from its parent."
    if any(mask and sid not in {current_user, SYSTEM, ADMINISTRATORS} for sid, mask in grants.items()):
        return "The private folder grants access to another user or group."
    if grants.get(current_user, 0) & FULL_ACCESS != FULL_ACCESS:
        return "The current Windows user lacks full access to the private folder."
    return None


@lru_cache(maxsize=1)
def _api():
    if os.name != "nt":
        raise StateError("Windows access checks require native Windows")
    kernel = C.WinDLL("kernel32", use_last_error=True)
    security = C.WinDLL("advapi32", use_last_error=True)
    def configure(library, name, result, arguments):
        function = getattr(library, name)
        function.restype = result
        function.argtypes = arguments
    configure(kernel, "GetCurrentProcess", PTR, [])
    configure(kernel, "CloseHandle", C.c_int, [PTR])
    configure(kernel, "LocalFree", PTR, [PTR])
    configure(kernel, "CreateDirectoryW", C.c_int, [C.c_wchar_p, C.POINTER(SecurityAttributes)])
    configure(security, "OpenProcessToken", C.c_int, [PTR, DWORD, C.POINTER(PTR)])
    configure(security, "GetTokenInformation", C.c_int, [PTR, C.c_int, PTR, DWORD, C.POINTER(DWORD)])
    configure(security, "ConvertSidToStringSidW", C.c_int, [PTR, C.POINTER(PTR)])
    configure(security, "ConvertStringSecurityDescriptorToSecurityDescriptorW", C.c_int,
              [C.c_wchar_p, DWORD, C.POINTER(PTR), PTR])
    configure(security, "GetNamedSecurityInfoW", DWORD,
              [C.c_wchar_p, C.c_int, DWORD, C.POINTER(PTR), PTR, C.POINTER(PTR), PTR, C.POINTER(PTR)])
    configure(security, "GetSecurityDescriptorControl", C.c_int, [PTR, C.POINTER(WORD), C.POINTER(DWORD)])
    configure(security, "GetAce", C.c_int, [PTR, DWORD, C.POINTER(PTR)])
    return kernel, security


def _check(ok, operation):
    if not ok:
        raise StateError(f"Windows {operation} failed (error {C.get_last_error()})")


def _sid_text(pointer) -> str:
    kernel, security = _api()
    text = PTR()
    _check(security.ConvertSidToStringSidW(pointer, C.byref(text)), "identity check")
    try:
        return C.wstring_at(text.value)
    finally:
        kernel.LocalFree(text)


def _current_sid() -> str:
    kernel, security = _api()
    token = PTR()
    _check(security.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, C.byref(token)), "token query")
    try:
        size = DWORD()
        security.GetTokenInformation(token, 1, None, 0, C.byref(size))  # TokenUser
        if not size.value:
            raise StateError("Windows token query returned no user identity")
        buffer = C.create_string_buffer(size.value)
        _check(security.GetTokenInformation(token, 1, buffer, size, C.byref(size)), "user query")
        return _sid_text(C.cast(buffer, C.POINTER(PTR)).contents.value)
    finally:
        kernel.CloseHandle(token)


def _native_path(path: Path) -> str:
    value = str(path.absolute())
    if value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value


def permission_issue(path: Path) -> str | None:
    kernel, security = _api()
    owner, acl, descriptor = PTR(), PTR(), PTR()
    code = security.GetNamedSecurityInfoW(_native_path(path), 1, 5, C.byref(owner), None,
                                         C.byref(acl), None, C.byref(descriptor))
    if code:
        raise StateError(f"Windows folder access query failed (error {code})")
    try:
        if not acl.value or not owner.value:
            return "The private folder has no restrictive access list or owner."
        control, revision = WORD(), DWORD()
        _check(security.GetSecurityDescriptorControl(descriptor, C.byref(control), C.byref(revision)), "access flags query")
        grants = {}
        for index in range(ACL.from_address(acl.value).count):
            ace = PTR()
            _check(security.GetAce(acl, index, C.byref(ace)), "access entry query")
            if C.c_uint8.from_address(ace.value).value != 0 or WORD.from_address(ace.value + 2).value < 12:
                return "The private folder has an unsupported access entry; owner review is required."
            sid = _sid_text(ace.value + 8)
            grants[sid] = grants.get(sid, 0) | DWORD.from_address(ace.value + 4).value
        return acl_issue(_sid_text(owner), _current_sid(), bool(control.value & 0x1000), grants)
    finally:
        kernel.LocalFree(descriptor)


def create_private_directory(path: Path) -> None:
    if os.name != "nt":
        path.mkdir(mode=0o700)
        return
    kernel, security = _api()
    sid = _current_sid()
    descriptor = PTR()
    sddl = f"O:{sid}D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
    _check(security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, C.byref(descriptor), None), "private access construction")
    try:
        attributes = SecurityAttributes(C.sizeof(SecurityAttributes), descriptor, 0)
        _check(kernel.CreateDirectoryW(_native_path(path), C.byref(attributes)), "private folder creation")
    finally:
        kernel.LocalFree(descriptor)
    issue = permission_issue(path)
    if issue:
        raise StateError(issue)


def private_temporary_directory(parent: Path, prefix: str) -> Path:
    path = parent / (prefix + uuid.uuid4().hex)
    create_private_directory(path)
    return path
