//! The launcher must offer recovery before the web UI can be started.
#[cfg(windows)]
pub fn choose_moved_library(error: &str) -> Option<std::path::PathBuf> {
    use std::ffi::c_void;
    #[repr(C)]
    struct BrowseInfo {
        owner: *mut c_void,
        root: *const c_void,
        display: *mut u16,
        title: *const u16,
        flags: u32,
        callback: *const c_void,
        parameter: isize,
        image: i32,
    }
    #[link(name = "user32")]
    unsafe extern "system" {
        fn MessageBoxW(owner: *mut c_void, text: *const u16, title: *const u16, flags: u32) -> i32;
    }
    #[link(name = "ole32")]
    unsafe extern "system" {
        fn OleInitialize(reserved: *mut c_void) -> i32;
        fn OleUninitialize();
        fn CoTaskMemFree(memory: *mut c_void);
    }
    #[link(name = "shell32")]
    unsafe extern "system" {
        fn SHBrowseForFolderW(info: *const BrowseInfo) -> *mut c_void;
        fn SHGetPathFromIDListEx(item: *const c_void, path: *mut u16, size: u32, flags: u32) -> i32;
    }
    let message: Vec<u16> = format!("{error}\n\n如果只是磁盘未连接，请连接后重新打开。\n如果移动了整个行影集文件夹，是否选择搬迁后的文件夹来恢复原快捷方式？\n取消会保留原设置，不会新建空图库。").encode_utf16().chain(Some(0)).collect();
    let title: Vec<u16> = "找回搬迁后的图库".encode_utf16().chain(Some(0)).collect();
    unsafe {
        if MessageBoxW(std::ptr::null_mut(), message.as_ptr(), title.as_ptr(), 0x24) != 6 {
            return None;
        }
        let initialized = OleInitialize(std::ptr::null_mut()) >= 0;
        let mut display = [0u16; 32768];
        let info = BrowseInfo {
            owner: std::ptr::null_mut(), root: std::ptr::null(), display: display.as_mut_ptr(),
            title: title.as_ptr(), flags: 0x41, callback: std::ptr::null(), parameter: 0, image: 0,
        };
        let item = SHBrowseForFolderW(&info);
        let result = if item.is_null() { None } else {
            let mut path = [0u16; 32768];
            let valid = SHGetPathFromIDListEx(item, path.as_mut_ptr(), path.len() as u32, 0) != 0;
            CoTaskMemFree(item);
            if valid {
                use std::os::windows::ffi::OsStringExt;
                let length = path.iter().position(|c| *c == 0).unwrap_or(path.len());
                Some(std::path::PathBuf::from(std::ffi::OsString::from_wide(&path[..length])))
            } else { None }
        };
        if initialized { OleUninitialize(); }
        result
    }
}
