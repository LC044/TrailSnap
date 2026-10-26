//! Legacy installer updates retain Tauri's signature verification and installer.
use crate::update_network;
use serde::Serialize;
use std::time::Duration;
use tauri::{ipc::Channel, Manager};
use tauri_plugin_updater::{Update, UpdaterExt};

#[derive(Default)]
pub struct InstalledUpdateState(tokio::sync::Mutex<Pending>);
#[derive(Default)]
struct Pending {
    update: Option<Update>,
    bytes: Option<Vec<u8>>,
}

#[derive(Clone, Serialize)]
#[serde(tag = "event", content = "data")]
pub enum DownloadEvent {
    #[serde(rename_all = "camelCase")]
    Started {
        content_length: Option<u64>,
    },
    #[serde(rename_all = "camelCase")]
    Progress {
        chunk_length: usize,
    },
    Finished,
}

#[tauri::command]
pub async fn desktop_installed_update_check(
    app: tauri::AppHandle,
) -> Result<Option<String>, String> {
    let _activity = crate::begin_activity(&app)?;
    let state = app.state::<InstalledUpdateState>();
    let mut pending = state.0.try_lock().map_err(|_| "更新操作正在进行")?;
    *pending = Pending::default();
    let sources = update_network::candidates(
        "https://github.com/LC044/TrailSnap/releases/latest/download/latest.json",
    );
    let update = update_network::first_valid(&sources, |url| {
        let app = app.clone();
        async move {
            app.updater_builder()
                .endpoints(vec![url.parse().map_err(|e| format!("{e}"))?])
                .map_err(|e| e.to_string())?
                .timeout(update_network::CATALOG_TIMEOUT)
                .configure_client(|client| {
                    client
                        .connect_timeout(Duration::from_secs(5))
                        .read_timeout(update_network::IDLE_TIMEOUT)
                })
                .build()
                .map_err(|e| e.to_string())?
                .check()
                .await
                .map_err(|e| e.to_string())
        }
    })
    .await?;
    let version = update.as_ref().map(|u| u.version.clone());
    pending.update = update;
    Ok(version)
}

#[tauri::command]
pub async fn desktop_installed_update_download(
    app: tauri::AppHandle,
    on_event: Channel<DownloadEvent>,
) -> Result<(), String> {
    let _activity = crate::begin_activity(&app)?;
    let state = app.state::<InstalledUpdateState>();
    let mut pending = state.0.try_lock().map_err(|_| "更新操作正在进行")?;
    pending.bytes = None;
    let mut update = pending.update.clone().ok_or("请先检查更新")?;
    let sources =
        update_network::rank(update_network::candidates(update.download_url.as_str())).await;
    let mut last_error = String::new();
    for round in 0..update_network::ROUNDS {
        update_network::backoff(round).await;
        for url in &sources {
            update.download_url = url.parse().map_err(|e| format!("{e}"))?;
            update.timeout = Some(Duration::from_secs(60 * 60));
            let _ = on_event.send(DownloadEvent::Started {
                content_length: None,
            });
            let mut started = false;
            let result = update
                .download(
                    |chunk_length, content_length| {
                        if !started {
                            let _ = on_event.send(DownloadEvent::Started { content_length });
                            started = true;
                        }
                        let _ = on_event.send(DownloadEvent::Progress { chunk_length });
                    },
                    || {},
                )
                .await;
            match result {
                Ok(bytes) => {
                    // Update::download returns bytes only after minisign verification.
                    pending.update = Some(update);
                    pending.bytes = Some(bytes);
                    let _ = on_event.send(DownloadEvent::Finished);
                    return Ok(());
                }
                Err(error) => last_error = error.to_string(),
            }
        }
    }
    Err(format!(
        "所有更新源下载失败（已自动重试），请稍后重试：{last_error}"
    ))
}

#[tauri::command]
pub async fn desktop_installed_update_install(app: tauri::AppHandle) -> Result<(), String> {
    let state = app.state::<InstalledUpdateState>();
    let mut pending = state.0.try_lock().map_err(|_| "更新操作正在进行")?;
    let update = pending.update.clone().ok_or("请先检查更新")?;
    let bytes = pending.bytes.take().ok_or("请先下载并校验更新")?;
    tauri::async_runtime::spawn_blocking(move || update.install(bytes))
        .await
        .map_err(|e| e.to_string())?
        .map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn progress_channel_preserves_the_frontend_event_contract() {
        assert_eq!(
            serde_json::to_value(DownloadEvent::Started {
                content_length: Some(100)
            })
            .unwrap(),
            serde_json::json!({"event": "Started", "data": {"contentLength": 100}})
        );
        assert_eq!(
            serde_json::to_value(DownloadEvent::Progress { chunk_length: 10 }).unwrap(),
            serde_json::json!({"event": "Progress", "data": {"chunkLength": 10}})
        );
        assert_eq!(
            serde_json::to_value(DownloadEvent::Finished).unwrap(),
            serde_json::json!({"event": "Finished"})
        );
    }
}
