fn main() {
    println!("cargo:rerun-if-changed=app.manifest");
    #[cfg(windows)]
    tauri_winres::WindowsResource::new()
        .set_icon("../src-tauri/icons/icon.ico")
        .set_manifest_file("app.manifest")
        .set("ProductName", "TrailSnap 行影集")
        .set("FileDescription", "行影集启动器")
        .compile()
        .expect("embed TrailSnap launcher icon");
}
