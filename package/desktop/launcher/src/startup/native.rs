use std::{
    fs,
    path::PathBuf,
    ptr::null_mut,
    sync::{
        atomic::{AtomicBool, AtomicIsize, AtomicU32, Ordering},
        Arc, Condvar, Mutex, OnceLock,
    },
    time::{Duration, Instant},
};
use windows_sys::Win32::{
    Foundation::*,
    Graphics::Gdi::*,
    System::{LibraryLoader::GetModuleHandleW, Threading::CreateMutexW},
    UI::{Controls::*, WindowsAndMessaging::*},
};
use windows_sys::{core::BOOL, Win32::UI::Input::KeyboardAndMouse::EnableWindow};

const WAKE: u32 = WM_APP + 31;
const REFRESH: u32 = WM_APP + 32;
const PAUSE: i32 = 101;
const RETRY: i32 = 102;
const LOGS: i32 = 103;
static STATE: OnceLock<Arc<State>> = OnceLock::new();

struct State {
    root: PathBuf,
    session: String,
    hwnd: AtomicIsize,
    child: AtomicU32,
    ready: AtomicBool,
    pausing: AtomicBool,
    migration_visible: AtomicBool,
    mode: Mutex<Option<String>>,
    displayed_error: Mutex<Option<String>>,
    decision: (Mutex<Option<bool>>, Condvar),
    started: Mutex<Instant>,
}

struct InstanceMutex(HANDLE);
impl Drop for InstanceMutex {
    fn drop(&mut self) {
        unsafe {
            CloseHandle(self.0);
        }
    }
}
fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain(Some(0)).collect()
}

pub fn session() -> Option<String> {
    STATE.get().map(|s| s.session.clone())
}
pub fn child(pid: u32) {
    if let Some(s) = STATE.get() {
        s.child.store(pid, Ordering::SeqCst);
    }
}
pub fn ready() {
    if let Some(s) = STATE.get() {
        s.ready.store(true, Ordering::SeqCst);
        unsafe {
            PostMessageW(s.hwnd.load(Ordering::SeqCst) as HWND, REFRESH, 0, 0);
        }
    }
}
pub fn stage(name: &str) {
    if let Some(s) = STATE.get() {
        let _ = crate::portable::write_json(
            &s.root.join("maintenance/automatic-upgrade-progress.json"),
            &serde_json::json!({"session":s.session,"stage":name,"cancellable":false}),
        );
        s.ready.store(false, Ordering::SeqCst);
        unsafe {
            PostMessageW(s.hwnd.load(Ordering::SeqCst) as HWND, REFRESH, 0, 0);
        }
    }
}

pub fn coordinate(run: fn() -> Result<(), String>) -> Result<(), String> {
    if std::env::args().any(|a| a == "--validate-only" || a == "--prepare-reinstall")
        || std::env::var("TS_DESKTOP_TEST_HEADLESS").as_deref() == Ok("1")
    {
        return run();
    }
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let root = crate::portable::clean_path(
        exe.parent()
            .ok_or("启动目录无效")?
            .canonicalize()
            .map_err(|e| e.to_string())?,
    );
    let identity = super::identity(&root);
    let handle =
        unsafe { CreateMutexW(null_mut(), 0, wide(&format!("Local\\{identity}")).as_ptr()) };
    if handle.is_null() {
        return Err(std::io::Error::last_os_error().to_string());
    }
    let exists = unsafe { GetLastError() == ERROR_ALREADY_EXISTS };
    let _mutex = InstanceMutex(handle);
    if exists {
        // The primary may still be creating its coordinator window.
        for _ in 0..100 {
            let hwnd = unsafe { FindWindowW(wide(&identity).as_ptr(), std::ptr::null()) };
            if !hwnd.is_null() {
                unsafe {
                    let mut pid = 0;
                    GetWindowThreadProcessId(hwnd, &mut pid);
                    AllowSetForegroundWindow(pid);
                    PostMessageW(hwnd, WAKE, 0, 0);
                }
                return Ok(());
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        return Err("行影集正在启动，请稍候再打开。".into());
    }
    // The UI and singleton must also survive an unwritable maintenance folder.
    // Filesystem errors are surfaced by run() inside this same native window.
    let state = Arc::new(State {
        root,
        session: uuid::Uuid::new_v4().to_string(),
        hwnd: AtomicIsize::new(0),
        child: AtomicU32::new(0),
        ready: AtomicBool::new(false),
        pausing: AtomicBool::new(false),
        migration_visible: AtomicBool::new(false),
        mode: Mutex::new(None),
        displayed_error: Mutex::new(None),
        decision: (Mutex::new(None), Condvar::new()),
        started: Mutex::new(Instant::now()),
    });
    STATE.set(state.clone()).map_err(|_| "启动窗口已存在")?;
    let (sender, receiver) = std::sync::mpsc::channel();
    let ui_state = state.clone();
    let ui = std::thread::spawn(move || unsafe { window(ui_state, &identity, sender) });
    receiver.recv().map_err(|e| e.to_string())??;
    stage("launching");
    loop {
        match run() {
            Ok(()) => break,
            Err(error) => {
                let _ = crate::portable::write_json(
                    &state.root.join("maintenance/launcher-error.json"),
                    &serde_json::json!({"error":error}),
                );
                *state.mode.lock().unwrap() = Some(error);
                state.ready.store(false, Ordering::SeqCst);
                unsafe {
                    PostMessageW(state.hwnd.load(Ordering::SeqCst) as HWND, REFRESH, 0, 0);
                }
                let mut choice = state.decision.0.lock().unwrap();
                while choice.is_none() {
                    choice = state.decision.1.wait(choice).unwrap();
                }
                if !choice.take().unwrap() {
                    break;
                }
                *state.mode.lock().unwrap() = None;
                *state.displayed_error.lock().unwrap() = None;
                state.pausing.store(false, Ordering::SeqCst);
                *state.started.lock().unwrap() = Instant::now();
                // A cancelled request belongs to this invocation, and must not cancel its retry.
                let cancel = state.root.join("maintenance/automatic-upgrade-cancel.json");
                if cancel.exists() {
                    fs::remove_file(cancel).map_err(|e| e.to_string())?;
                }
                stage("launching");
            }
        }
    }
    unsafe {
        PostMessageW(state.hwnd.load(Ordering::SeqCst) as HWND, WM_DESTROY, 0, 0);
    }
    let _ = ui.join();
    Ok(())
}

unsafe fn set_text(hwnd: HWND, id: i32, value: &str) {
    SetWindowTextW(GetDlgItem(hwnd, id), wide(value).as_ptr());
}
unsafe fn reveal(hwnd: HWND) {
    if std::env::var("TS_DESKTOP_TEST_HIDE_WINDOW").as_deref() == Ok("1") {
        return;
    }
    ShowWindow(
        hwnd,
        if IsIconic(hwnd) != 0 {
            SW_RESTORE
        } else {
            SW_SHOW
        },
    );
    SetForegroundWindow(hwnd);
}
unsafe extern "system" fn focus_child(hwnd: HWND, pointer: LPARAM) -> BOOL {
    let mut pid = 0;
    GetWindowThreadProcessId(hwnd, &mut pid);
    // WebView also creates ownerless helper windows. Restore the application's
    // titled, ordinary top-level window rather than whichever helper enumerates first.
    if pid == pointer as u32
        && IsWindowVisible(hwnd) != 0
        && GetWindow(hwnd, GW_OWNER).is_null()
        && GetWindowTextLengthW(hwnd) > 0
        && GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW as isize == 0
    {
        reveal(hwnd);
        return 0;
    }
    1
}
unsafe fn wake(hwnd: HWND, state: &State) {
    if state.mode.lock().unwrap().is_some() {
        reveal(hwnd);
    } else if !state.ready.load(Ordering::SeqCst) && state.migration_visible.load(Ordering::SeqCst)
    {
        reveal(hwnd);
    } else if state.child.load(Ordering::SeqCst) != 0 {
        EnumWindows(
            Some(focus_child),
            state.child.load(Ordering::SeqCst) as LPARAM,
        );
    }
}

fn bytes(value: u64) -> String {
    if value >= 1024 * 1024 * 1024 {
        format!("{:.2} GB", value as f64 / (1024.0 * 1024.0 * 1024.0))
    } else {
        format!("{:.1} MB", value as f64 / (1024.0 * 1024.0))
    }
}
unsafe fn render(hwnd: HWND, state: &State) {
    if state.ready.load(Ordering::SeqCst) {
        ShowWindow(hwnd, SW_HIDE);
        return;
    }
    let error = state.mode.lock().unwrap().clone();
    if let Some(error) = error {
        let mut displayed = state.displayed_error.lock().unwrap();
        if displayed.as_ref() == Some(&error) {
            return;
        }
        *displayed = Some(error.clone());
        let paused = error.contains("TRAILSNAP_UPGRADE_PAUSED:");
        set_text(
            hwnd,
            1,
            if paused {
                "升级已安全暂停"
            } else {
                "行影集暂时未能打开"
            },
        );
        set_text(hwnd, 2, &error.replace("TRAILSNAP_UPGRADE_PAUSED:", ""));
        MoveWindow(GetDlgItem(hwnd, 2), 24, 60, 540, 85, 1);
        set_text(
            hwnd,
            4,
            "本次启动已停止。可重试，或稍后重新打开行影集。未完成的复制会重新进行。",
        );
        set_text(hwnd, PAUSE, "退出");
        EnableWindow(GetDlgItem(hwnd, PAUSE), 1);
        ShowWindow(GetDlgItem(hwnd, RETRY), SW_SHOW);
        ShowWindow(GetDlgItem(hwnd, LOGS), SW_SHOW);
        ShowWindow(GetDlgItem(hwnd, 3), SW_HIDE);
        if IsWindowVisible(hwnd) == 0 {
            reveal(hwnd);
        }
        return;
    }
    let path = state
        .root
        .join("maintenance/automatic-upgrade-progress.json");
    let value = crate::portable::read_json::<serde_json::Value>(&path)
        .ok()
        .filter(|v| v["session"] == state.session)
        .unwrap_or_default();
    let stage = value["stage"].as_str().unwrap_or("launching");
    let migrating = super::is_migration_stage(stage);
    // Discovery alone is not a migration. Keep ordinary launches invisible;
    // reveal once real migration starts without restoring a minimized window
    // on every progress tick. A stale session cannot trigger this path.
    let reveal_migration = migrating && !state.migration_visible.swap(true, Ordering::SeqCst);
    MoveWindow(GetDlgItem(hwnd, 2), 24, 60, 540, 50, 1);
    set_text(hwnd, 1, super::label(stage));
    let elapsed = state.started.lock().unwrap().elapsed().as_secs();
    let done = value["completed"].as_u64().unwrap_or(0);
    let total = value["total"].as_u64().unwrap_or(0);
    let cancellable = value["cancellable"] == true && !state.pausing.load(Ordering::SeqCst);
    let unit = value["unit"].as_str().unwrap_or("files");
    let counts = if total > 0 {
        if unit == "bytes" {
            let seconds = value["elapsedSeconds"].as_f64().unwrap_or(0.0);
            let speed = if seconds >= 1.0 {
                format!("，处理速度 {}/秒", bytes((done as f64 / seconds) as u64))
            } else {
                String::new()
            };
            format!(
                "已处理 {} / {}（含复制和校验）{}",
                bytes(done),
                bytes(total),
                speed
            )
        } else {
            format!(
                "已校验 {done} / {total} {}",
                if unit == "photos" {
                    "张照片"
                } else {
                    "个文件"
                }
            )
        }
    } else if done > 0 {
        format!(
            "已检查 {done} {}，正在继续…",
            if unit == "photos" {
                "张照片"
            } else {
                "个文件"
            }
        )
    } else {
        "正在处理，请稍候…".into()
    };
    set_text(
        hwnd,
        2,
        &format!("{counts}\n已用时 {} 分 {} 秒", elapsed / 60, elapsed % 60),
    );
    set_text(
        hwnd,
        4,
        if state.pausing.load(Ordering::SeqCst) {
            "正在等待当前文件安全停止，请稍候…"
        } else if cancellable {
            "正在升级旧版本数据，完成后自动打开。大图库可能需要较长时间。可安全暂停后稍后继续；未完成的复制需重做。"
        } else if migrating {
            "正在准备或完成升级，请保持磁盘连接。此阶段完成前请勿结束进程，窗口仍可最小化。"
        } else {
            "正在启动行影集，完成后自动打开。"
        },
    );
    set_text(hwnd, PAUSE, "稍后继续");
    EnableWindow(GetDlgItem(hwnd, PAUSE), cancellable as BOOL);
    ShowWindow(GetDlgItem(hwnd, RETRY), SW_HIDE);
    ShowWindow(GetDlgItem(hwnd, LOGS), SW_HIDE);
    ShowWindow(GetDlgItem(hwnd, 3), SW_SHOW);
    let progress = GetDlgItem(hwnd, 3);
    let style = GetWindowLongPtrW(progress, GWL_STYLE);
    let next_style = if total == 0 {
        style | PBS_MARQUEE as isize
    } else {
        style & !(PBS_MARQUEE as isize)
    };
    if style != next_style {
        SetWindowLongPtrW(progress, GWL_STYLE, next_style);
        SendMessageW(progress, PBM_SETMARQUEE, (total == 0) as WPARAM, 40);
    }
    if total > 0 {
        SendMessageW(
            progress,
            PBM_SETPOS,
            ((done.min(total) as u128 * 100) / total as u128) as WPARAM,
            0,
        );
    }
    if reveal_migration {
        reveal(hwnd);
    }
}

unsafe extern "system" fn procedure(hwnd: HWND, message: u32, wp: WPARAM, lp: LPARAM) -> LRESULT {
    if message == WM_NCCREATE {
        let create = &*(lp as *const CREATESTRUCTW);
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, create.lpCreateParams as isize);
    }
    let pointer = GetWindowLongPtrW(hwnd, GWLP_USERDATA) as *const State;
    if pointer.is_null() {
        return DefWindowProcW(hwnd, message, wp, lp);
    }
    let state = &*pointer;
    match message {
        WM_CTLCOLORSTATIC => {
            SetBkMode(wp as HDC, TRANSPARENT as i32);
            SetTextColor(wp as HDC, GetSysColor(COLOR_WINDOWTEXT));
            GetSysColorBrush(COLOR_WINDOW) as LRESULT
        }
        WM_TIMER => {
            render(hwnd, state);
            0
        }
        REFRESH => {
            render(hwnd, state);
            if state.mode.lock().unwrap().is_some() {
                reveal(hwnd);
            }
            0
        }
        WAKE => {
            wake(hwnd, state);
            0
        }
        WM_CLOSE => {
            if state.mode.lock().unwrap().is_some() {
                *state.decision.0.lock().unwrap() = Some(false);
                state.decision.1.notify_one();
            } else {
                let progress = crate::portable::read_json::<serde_json::Value>(
                    &state
                        .root
                        .join("maintenance/automatic-upgrade-progress.json"),
                )
                .ok();
                if progress
                    .is_some_and(|v| v["session"] == state.session && v["cancellable"] == true)
                {
                    PostMessageW(hwnd, WM_COMMAND, PAUSE as WPARAM, 0);
                } else {
                    ShowWindow(hwnd, SW_MINIMIZE);
                }
            }
            0
        }
        WM_COMMAND => {
            match (wp & 0xffff) as i32 {
                PAUSE => {
                    if state.mode.lock().unwrap().is_some() {
                        *state.decision.0.lock().unwrap() = Some(false);
                        state.decision.1.notify_one();
                    } else {
                        state.pausing.store(true, Ordering::SeqCst);
                        let _ = crate::portable::write_json(
                            &state.root.join("maintenance/automatic-upgrade-cancel.json"),
                            &serde_json::json!({"session":state.session}),
                        );
                        EnableWindow(GetDlgItem(hwnd, PAUSE), 0);
                        set_text(hwnd, 4, "正在等待当前文件安全停止，请稍候…");
                    }
                }
                RETRY => {
                    if state.mode.lock().unwrap().is_some() {
                        *state.decision.0.lock().unwrap() = Some(true);
                        state.decision.1.notify_one();
                    }
                }
                LOGS => {
                    let maintenance = state.root.join("maintenance");
                    let _ = std::process::Command::new("explorer.exe")
                        .arg(if maintenance.is_dir() {
                            maintenance
                        } else {
                            state.root.clone()
                        })
                        .spawn();
                }
                _ => {}
            }
            0
        }
        WM_DESTROY => {
            PostQuitMessage(0);
            0
        }
        _ => DefWindowProcW(hwnd, message, wp, lp),
    }
}

unsafe fn window(
    state: Arc<State>,
    identity: &str,
    sender: std::sync::mpsc::Sender<Result<(), String>>,
) {
    let instance = GetModuleHandleW(std::ptr::null());
    let class = wide(identity);
    let wc = WNDCLASSW {
        lpfnWndProc: Some(procedure),
        hInstance: instance,
        lpszClassName: class.as_ptr(),
        hIcon: LoadIconW(instance, 32512 as _),
        hCursor: LoadCursorW(null_mut(), IDC_ARROW),
        hbrBackground: (COLOR_WINDOW + 1) as _,
        ..std::mem::zeroed()
    };
    if RegisterClassW(&wc) == 0 {
        let _ = sender.send(Err(std::io::Error::last_os_error().to_string()));
        return;
    }
    InitCommonControlsEx(&INITCOMMONCONTROLSEX {
        dwSize: std::mem::size_of::<INITCOMMONCONTROLSEX>() as u32,
        dwICC: ICC_PROGRESS_CLASS,
    });
    let hwnd = CreateWindowExW(
        0,
        class.as_ptr(),
        wide("行影集").as_ptr(),
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        600,
        335,
        null_mut(),
        null_mut(),
        instance,
        Arc::as_ptr(&state) as _,
    );
    if hwnd.is_null() {
        let _ = sender.send(Err(std::io::Error::last_os_error().to_string()));
        return;
    }
    let mut work: RECT = std::mem::zeroed();
    if SystemParametersInfoW(SPI_GETWORKAREA, 0, &mut work as *mut _ as _, 0) != 0 {
        SetWindowPos(
            hwnd,
            null_mut(),
            work.left + ((work.right - work.left - 600) / 2).max(0),
            work.top + ((work.bottom - work.top - 335) / 2).max(0),
            0,
            0,
            SWP_NOSIZE | SWP_NOZORDER,
        );
    }
    state.hwnd.store(hwnd as isize, Ordering::SeqCst);
    let font = CreateFontW(
        -16,
        0,
        0,
        0,
        400,
        0,
        0,
        0,
        DEFAULT_CHARSET as u32,
        OUT_DEFAULT_PRECIS as u32,
        CLIP_DEFAULT_PRECIS as u32,
        CLEARTYPE_QUALITY as u32,
        DEFAULT_PITCH as u32,
        wide("Microsoft YaHei UI").as_ptr(),
    );
    let heading_font = CreateFontW(
        -19,
        0,
        0,
        0,
        600,
        0,
        0,
        0,
        DEFAULT_CHARSET as u32,
        OUT_DEFAULT_PRECIS as u32,
        CLIP_DEFAULT_PRECIS as u32,
        CLEARTYPE_QUALITY as u32,
        DEFAULT_PITCH as u32,
        wide("Microsoft YaHei UI").as_ptr(),
    );
    for (id, class, text, x, y, width, height, style) in [
        (1, "STATIC", "正在启动行影集…", 24, 22, 540, 28, 0),
        (
            2,
            "EDIT",
            "正在处理，请稍候…",
            24,
            60,
            540,
            50,
            (ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL) as u32,
        ),
        (3, "msctls_progress32", "", 24, 116, 540, 18, PBS_MARQUEE),
        (4, "STATIC", "正在启动行影集…", 24, 150, 540, 68, 0),
        (
            PAUSE,
            "BUTTON",
            "稍后继续",
            444,
            244,
            120,
            30,
            BS_PUSHBUTTON as u32,
        ),
        (
            RETRY,
            "BUTTON",
            "重试",
            314,
            244,
            120,
            30,
            BS_PUSHBUTTON as u32,
        ),
        (
            LOGS,
            "BUTTON",
            "查看日志",
            24,
            244,
            120,
            30,
            BS_PUSHBUTTON as u32,
        ),
    ] {
        let control = CreateWindowExW(
            0,
            wide(class).as_ptr(),
            wide(text).as_ptr(),
            WS_CHILD
                | WS_VISIBLE
                | style
                | if class == "BUTTON" || class == "EDIT" {
                    WS_TABSTOP
                } else {
                    0
                },
            x,
            y,
            width,
            height,
            hwnd,
            id as _,
            instance,
            null_mut(),
        );
        SendMessageW(
            control,
            WM_SETFONT,
            if id == 1 { heading_font } else { font } as WPARAM,
            1,
        );
    }
    SetTimer(hwnd, 1, 250, None);
    SendMessageW(GetDlgItem(hwnd, 3), PBM_SETMARQUEE, 1, 40);
    render(hwnd, &state);
    let _ = sender.send(Ok(()));
    let mut message: MSG = std::mem::zeroed();
    while GetMessageW(&mut message, null_mut(), 0, 0) > 0 {
        if IsDialogMessageW(hwnd, &message) == 0 {
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
    }
    DestroyWindow(hwnd);
    DeleteObject(font);
    DeleteObject(heading_font);
}
