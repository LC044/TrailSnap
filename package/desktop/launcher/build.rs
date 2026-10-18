fn main() {
    #[cfg(windows)]
    tauri_winres::WindowsResource::new()
        .set_icon("../src-tauri/icons/icon.ico")
        .set("ProductName", "TrailSnap 行影集")
        .set("FileDescription", "行影集启动器")
        .compile()
        .expect("embed TrailSnap launcher icon");
}
