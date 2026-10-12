//! Coordinates worker result persistence, Gateway requests and model downloads.
use crate::{ai_gateway::AIGateway, RuntimeStatus};
use serde_json::{json, Value};
use std::{
    sync::{Arc, Mutex},
    time::Duration,
};

#[derive(Clone)]
pub struct ExtensionLifecycle {
    pub server_status: Arc<Mutex<RuntimeStatus>>,
    pub gateway: AIGateway,
}

impl ExtensionLifecycle {
    pub async fn requirements(&self) -> Result<crate::ai_extension::ServerRequirements, String> {
        let status = self
            .server_status
            .lock()
            .expect("desktop status poisoned")
            .clone();
        if !status.ready {
            return Err("本地服务尚未就绪，请稍后重试".into());
        }
        let response = reqwest::Client::builder()
            .no_proxy()
            .build()
            .map_err(|e| e.to_string())?
            .get(format!(
                "{}/api/system/desktop/ai-extension",
                status.api_url
            ))
            .header("X-TrailSnap-Desktop-Secret", status.session_secret)
            .timeout(Duration::from_secs(15))
            .send()
            .await
            .map_err(|e| format!("无法读取 Server 的 AI 扩展版本要求：{e}"))?;
        if !response.status().is_success() {
            return Err(format!(
                "Server AI 扩展版本接口返回 HTTP {}",
                response.status()
            ));
        }
        let payload: Value = response.json().await.map_err(|e| e.to_string())?;
        if payload["code"] != 0 {
            return Err("Server AI 扩展版本接口返回错误".into());
        }
        serde_json::from_value(payload["data"].clone())
            .map_err(|e| format!("Server AI 扩展版本信息无效：{e}"))
    }

    pub async fn set_state(&self, state: &str) -> Result<(), String> {
        let status = self
            .server_status
            .lock()
            .expect("desktop status poisoned")
            .clone();
        if !status.ready {
            return Err("本地服务尚未就绪，请稍后重试".into());
        }
        let response = reqwest::Client::builder()
            .no_proxy()
            .build()
            .map_err(|e| e.to_string())?
            .post(format!(
                "{}/api/system/desktop/ai-extension",
                status.api_url
            ))
            .header("X-TrailSnap-Desktop-Secret", status.session_secret)
            .json(&json!({ "state": state }))
            // Draining large inference batches must not have a short timeout.
            .timeout(Duration::from_secs(24 * 60 * 60))
            .send()
            .await
            .map_err(|e| format!("无法协调 AI 扩展维护：{e}"))?;
        if !response.status().is_success() {
            return Err(format!("AI 扩展维护接口返回 HTTP {}", response.status()));
        }
        let payload: Value = response.json().await.map_err(|e| e.to_string())?;
        if payload["code"] != 0 {
            return Err(payload["msg"].as_str().unwrap_or("AI 扩展维护失败").into());
        }
        Ok(())
    }

    pub async fn begin(&self) -> Result<(), String> {
        // Stop dispatch and finish result commits before closing Gateway admission.
        self.set_state("maintenance").await?;
        self.gateway.drain_for_extension().await
    }

    pub async fn finish(&self, state: &str) -> Result<(), String> {
        self.gateway
            .finish_extension_maintenance(state == "waiting_update");
        self.set_state(state).await
    }
}
