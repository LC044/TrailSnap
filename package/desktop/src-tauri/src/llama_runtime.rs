use crate::{hardware, update_network};
use sha2::{Digest, Sha256};
use std::{
    env, fs, io,
    path::{Path, PathBuf},
    time::Duration,
};

const LLAMA_BUILD: &str = "b12651";
const EXECUTABLE: &str = if cfg!(windows) {
    "llama-server.exe"
} else {
    "llama-server"
};

pub fn managed_runtime_dir() -> Option<PathBuf> {
    env::var_os("TS_DESKTOP_ROOT")
        .map(PathBuf::from)
        .map(|root| root.join("runtime/llama.cpp").join(LLAMA_BUILD))
}

fn managed_npu_runtime_dir() -> Option<PathBuf> {
    managed_runtime_dir().map(|path| path.with_file_name(format!("{LLAMA_BUILD}-openvino-npu")))
}

pub fn find_llama_server() -> Option<PathBuf> {
    if let Some(path) = env::var_os("LLAMA_SERVER_PATH")
        .map(PathBuf::from)
        .filter(|path| path.is_file())
    {
        return Some(path);
    }
    if let Some(root) = managed_runtime_dir() {
        return find_file_named(&root, EXECUTABLE);
    }
    env::split_paths(&env::var_os("PATH")?)
        .map(|dir| dir.join(EXECUTABLE))
        .find(|path| path.is_file())
}

pub async fn install(npu: bool) -> Result<(), String> {
    if !npu && find_llama_server().is_some() {
        return Ok(());
    }
    let target = if npu { managed_npu_runtime_dir() } else { managed_runtime_dir() }
        .ok_or("无法读取桌面数据目录")?;
    if npu && find_file_named(&target, EXECUTABLE).is_some() {
        return Ok(());
    }
    let parent = target.parent().ok_or("运行时目录无效")?;
    fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    let mut errors = Vec::new();
    let candidates = if npu {
        vec![Package::new(
            "win-openvino-2026.4.1-x64.zip",
            "741dac28961296df719e8d1c591a9967802e8691cb3234299ef9dcd5783ce563",
            false,
        )]
    } else {
        packages().await
    };
    for package in candidates {
        let work = parent.join(format!(".download-{}", uuid::Uuid::new_v4()));
        fs::create_dir(&work).map_err(|error| error.to_string())?;
        let result = install_package(&package, &work, &target).await;
        let _ = fs::remove_dir_all(&work);
        match result {
            Ok(()) => return Ok(()),
            Err(error) => errors.push(format!("{}：{error}", package.suffix)),
        }
    }
    if errors.is_empty() {
        return Err("当前平台没有可用的 llama.cpp 预编译包".into());
    }
    Err(format!("无法准备本地大模型环境（{}）", errors.join("；")))
}

struct Package {
    suffix: &'static str,
    sha256: &'static str,
    gpu: bool,
    dependencies: Option<(&'static str, &'static str)>,
}

impl Package {
    fn new(suffix: &'static str, sha256: &'static str, gpu: bool) -> Self {
        Self {
            suffix,
            sha256,
            gpu,
            dependencies: None,
        }
    }

    fn cuda(mut self, name: &'static str, sha256: &'static str) -> Self {
        self.dependencies = Some((name, sha256));
        self
    }
}

async fn packages() -> Vec<Package> {
    let mut packages = Vec::new();
    let (os, arch) = (env::consts::OS, env::consts::ARCH);
    #[cfg(not(target_os = "macos"))]
    {
        let nvidia = hardware::cuda_devices().await.unwrap_or_default();
        if hardware::cuda_compatible(&nvidia, 580, (10, 0)) {
            let modern_cuda = match (os, arch) {
                ("windows", "x86_64") => Some(
                    Package::new(
                        "win-cuda-13.5-x64.zip",
                        "5ad87e0771f3a129f6461b5fc706d8c2c5e5b71b2bd1f953a4221ca4d7797fef",
                        true,
                    )
                    .cuda(
                        "cudart-llama-bin-win-cuda-13.5-x64.zip",
                        "c2bf4cc202bfbaaa7a0b75f5082457c3811326947bb216059b72839d844e9cba",
                    ),
                ),
                ("linux", "x86_64") => Some(
                    Package::new(
                        "ubuntu-cuda-13.5-x64.tar.gz",
                        "78ffa8d39ee0e54108a33b9f81affca3748e4e1d079d7d8b03368ab6986c6c76",
                        true,
                    )
                    .cuda(
                        "cudart-llama-b12651-bin-ubuntu-cuda-13.5-x64.tar.gz",
                        "73bd842d8d178f2ad7a8053eb218a94e0ba9e991965584d0b7af9135cde2d7c6",
                    ),
                ),
                _ => None,
            };
            packages.extend(modern_cuda);
        }
        let cuda = match (os, arch) {
            ("windows", "x86_64") => Some((
                528,
                (6, 0),
                Package::new(
                    "win-cuda-12.4-x64.zip",
                    "1a6c090f76fab41260b5b7597c6fb1add1fad2efaac692ae2673a22366220a29",
                    true,
                )
                .cuda(
                    "cudart-llama-bin-win-cuda-12.4-x64.zip",
                    "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6",
                ),
            )),
            ("windows", "aarch64") => Some((
                580,
                (7, 5),
                Package::new(
                    "win-cuda-13.5-arm64.zip",
                    "d09eea1cf58f99debec50c1a7e2189677cf0be9565847720a08cf53a0cc71c11",
                    true,
                )
                .cuda(
                    "cudart-llama-bin-win-cuda-13.5-arm64.zip",
                    "f89e7b2457f627d052dd99f42205ddfd01964454809754cdc649cffc74320dca",
                ),
            )),
            ("linux", "x86_64") => Some((
                525,
                (6, 0),
                Package::new(
                    "ubuntu-cuda-12.8-x64.tar.gz",
                    "cb099350c6a025e67eefaa13f2b67b2dcce53e38a0da22476e070d166ef367ea",
                    true,
                )
                .cuda(
                    "cudart-llama-b12651-bin-ubuntu-cuda-12.8-x64.tar.gz",
                    "485df8f0b0ab30c15807d25fd23a821aeaef62a3947722c683429491a5e0d027",
                ),
            )),
            ("linux", "aarch64") => Some((
                580,
                (7, 5),
                Package::new(
                    "ubuntu-cuda-13.5-arm64.tar.gz",
                    "e631c7a4b665bc123040f2edbd8e2084686ce497d5d3e7e6afe356cfa",
                    true,
                )
                .cuda(
                    "cudart-llama-b12651-bin-ubuntu-cuda-13.5-arm64.tar.gz",
                    "1781bd5577c4439aea5f5e7f8bcac9f85b670c5c98529fe9f7c53b92d0e91442",
                ),
            )),
            _ => None,
        };
        if let Some((driver, compute, package)) = cuda {
            if hardware::cuda_compatible(&nvidia, driver, compute) {
                packages.push(package);
            }
        }
    }
    #[cfg(windows)]
    if arch == "x86_64"
        && env::var_os("HIP_PATH").is_some()
        && hardware::display_devices().await.contains("VEN_1002")
    {
        packages.push(Package::new(
            "win-rocm-10.0-x64.zip",
            "2773845442fee43a21031f6d264bc1f41a870be7980892e2cd7a2d46cedc30bd",
            true,
        ));
    }
    #[cfg(target_os = "linux")]
    if arch == "x86_64"
        && hardware::probe("rocminfo", &[], 5)
            .await
            .is_some_and(|info| {
                info.lines().any(|line| {
                    line.split_once(':').is_some_and(|(key, value)| {
                        key.trim() == "Device Type" && value.trim() == "GPU"
                    })
                })
            })
    {
        packages.push(Package::new(
            "ubuntu-rocm-10.0-x64.tar.gz",
            "f378f66f77d219ae3215f9b8d4ee366f9974782b8aec4fda88464c55a3250ced",
            true,
        ));
    }
    #[cfg(not(target_os = "macos"))]
    if vulkan_supported().await {
        let vulkan = match (os, arch) {
            ("windows", "x86_64") => Some((
                "win-vulkan-x64.zip",
                "e58fa9a137d8046c69334005ad6fb3e904ddc7e56f2a61ad1b844335826ef3f4",
            )),
            ("windows", "aarch64") => Some((
                "win-vulkan-arm64.zip",
                "430849ca03a2a891baa90091670df45f29b90c2ec445aab2ad7d830ff423303c",
            )),
            ("linux", "x86_64") => Some((
                "ubuntu-vulkan-x64.tar.gz",
                "0bbcf2093f15c64c8a9bf54b809c9b2c812b982992dc2fbc9b36720c1d32cf13",
            )),
            ("linux", "aarch64") => Some((
                "ubuntu-vulkan-arm64.tar.gz",
                "138f97d9d448b7a55c4b839366bba6e2ac7fba634f9160c9a4775a2051a1c7cb",
            )),
            _ => None,
        };
        if let Some((suffix, sha256)) = vulkan {
            packages.push(Package::new(suffix, sha256, true));
        }
    }
    let baseline = match (os, arch) {
        ("windows", "x86_64") => Some((
            "win-cpu-x64.zip",
            "b2d794fa7587aba29f654d717ff9b73e31caeabf50a7766692903008bbe0855d",
        )),
        ("windows", "aarch64") => Some((
            "win-cpu-arm64.zip",
            "756a62761e476536f007c866d46fa14125f6ca32d98cee6af14685659bd9f244",
        )),
        ("linux", "x86_64") => Some((
            "ubuntu-x64.tar.gz",
            "17b242259181d5b1b1f7719aba27929700a8b0dab39bfaef1b971a992b397b38",
        )),
        ("linux", "aarch64") => Some((
            "ubuntu-arm64.tar.gz",
            "b4a8d17e16a1b42f6a1395dc5cd6967ec0d98005eb3be85b7eb893b082306ed4",
        )),
        ("macos", "x86_64") => Some((
            "macos-x64.tar.gz",
            "34c19771545479a783d3b68c446383ab703033890c052d3ff0b860a5c9f59e56",
        )),
        ("macos", "aarch64") => Some((
            "macos-arm64.tar.gz",
            "264fd872de61679c45ad57e1e21c2a2a54e29b35734ecf3d50f24166447ab8d2",
        )),
        _ => None,
    };
    if let Some((suffix, sha256)) = baseline {
        // The macOS build includes Metal and can fall back to CPU internally.
        packages.push(Package::new(suffix, sha256, false));
    }
    packages
}

#[cfg(windows)]
async fn vulkan_supported() -> bool {
    env::var_os("SystemRoot")
        .is_some_and(|root| PathBuf::from(root).join("System32/vulkan-1.dll").is_file())
}

#[cfg(all(not(windows), not(target_os = "macos")))]
async fn vulkan_supported() -> bool {
    if let Some(info) = hardware::probe("vulkaninfo", &["--summary"], 5).await {
        return info.contains("PHYSICAL_DEVICE_TYPE_DISCRETE_GPU")
            || info.contains("PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU");
    }
    fs::read_dir("/dev/dri").is_ok_and(|entries| {
        entries
            .flatten()
            .any(|entry| entry.file_name().to_string_lossy().starts_with("renderD"))
    })
}

async fn install_package(
    package: &Package,
    work: &Path,
    target: &Path,
) -> Result<(), String> {
    let stage = work.join("runtime");
    fs::create_dir(&stage).map_err(|error| error.to_string())?;
    let name = format!("llama-{LLAMA_BUILD}-bin-{}", package.suffix);
    download_and_extract(&name, package.sha256, work, &stage).await?;
    let executable = find_file_named(&stage, EXECUTABLE).ok_or("压缩包缺少 llama-server")?;
    if let Some((name, sha256)) = package.dependencies {
        let bin = executable.parent().ok_or("可执行文件路径无效")?;
        if let Some(directory) = name.strip_suffix(".tar.gz") {
            let dependencies = work.join("dependencies");
            fs::create_dir(&dependencies).map_err(|error| error.to_string())?;
            download_and_extract(name, sha256, work, &dependencies).await?;
            for entry in
                fs::read_dir(dependencies.join(directory)).map_err(|error| error.to_string())?
            {
                let entry = entry.map_err(|error| error.to_string())?;
                fs::rename(entry.path(), bin.join(entry.file_name()))
                    .map_err(|error| error.to_string())?;
            }
        } else {
            download_and_extract(name, sha256, work, bin).await?;
        }
    }
    let version = hardware::probe(&executable, &["--version"], 20)
        .await
        .ok_or("llama-server 无法启动")?;
    if !is_expected_version(&version) {
        return Err("llama-server 版本校验失败".into());
    }
    if package.gpu
        && !hardware::probe(&executable, &["--list-devices"], 25)
            .await
            .is_some_and(|output| has_gpu(&output))
    {
        return Err("运行时没有检测到可用的 GPU".into());
    }

    match fs::rename(&stage, target) {
        Ok(()) => Ok(()),
        Err(_) if find_file_named(target, EXECUTABLE).is_some() => Ok(()),
        Err(error) => Err(format!("无法启用 llama.cpp 运行时：{error}")),
    }
}

fn is_expected_version(output: &str) -> bool {
    let build = LLAMA_BUILD.trim_start_matches('b');
    let stamp = format!("(build {build},");
    output
        .lines()
        .any(|line| line.starts_with("version: ") && line.contains(&stamp))
}

fn has_gpu(output: &str) -> bool {
    output
        .lines()
        .skip_while(|line| line.trim() != "Available devices:")
        .skip(1)
        .any(|line| {
            let line = line.to_ascii_lowercase();
            line.starts_with("  ")
                && line.contains(" mib,")
                && !line.contains("(0 mib,")
                && !["llvmpipe", "softpipe", "swiftshader"]
                    .iter()
                    .any(|name| line.contains(name))
        })
}

async fn download_and_extract(
    name: &str,
    expected: &'static str,
    work: &Path,
    stage: &Path,
) -> Result<(), String> {
    let url =
        format!("https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/{name}");
    let archive = work.join(name);
    update_network::Download {
        destination: &archive,
        size: None,
        timeout: Duration::from_secs(900),
    }
    .verified(
        update_network::llama_candidates(&url),
        update_network::DownloadMode::desktop(),
        |_, _| {},
        |archive| {
            let name = name.to_owned();
            async move {
                tauri::async_runtime::spawn_blocking(move || {
                    let mut file = fs::File::open(archive).map_err(|error| error.to_string())?;
                    let mut hash = Sha256::new();
                    io::copy(&mut file, &mut hash).map_err(|error| error.to_string())?;
                    if format!("{:x}", hash.finalize()) != expected {
                        return Err(format!("{name} 校验失败"));
                    }
                    Ok(())
                })
                .await
                .map_err(|error| error.to_string())?
            }
        },
    )
    .await?;
    let stage = stage.to_path_buf();
    let zip = name.ends_with(".zip");
    tauri::async_runtime::spawn_blocking(move || unpack(&archive, &stage, zip))
        .await
        .map_err(|error| error.to_string())?
}

fn unpack(archive: &Path, stage: &Path, zip: bool) -> Result<(), String> {
    let file = fs::File::open(archive).map_err(|error| error.to_string())?;
    if zip {
        zip::ZipArchive::new(file)
            .and_then(|mut archive| archive.extract(stage))
            .map_err(|error| error.to_string())?;
    } else {
        tar::Archive::new(flate2::read::GzDecoder::new(file))
            .unpack(stage)
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}
fn find_file_named(root: &Path, name: &str) -> Option<PathBuf> {
    let entries = fs::read_dir(root).ok()?;
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file()
            && entry
                .file_name()
                .to_string_lossy()
                .eq_ignore_ascii_case(name)
        {
            return Some(path);
        }
        if path.is_dir() {
            if let Some(found) = find_file_named(&path, name) {
                return Some(found);
            }
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn checks_the_build_stamp_emitted_by_the_release_binary() {
        assert!(is_expected_version(
            "version: 1.0.0-dev (build 12651, commit f5e6915c2)"
        ));
        assert!(!is_expected_version(
            "version: 1.0.0-dev (build 126510, commit f5e6915c2)"
        ));
    }

    #[test]
    fn gpu_check_ignores_software_drivers_and_empty_device_lists() {
        assert!(has_gpu(
            "Available devices:\n  Vulkan0: AMD Radeon (8192 MiB, 7000 MiB free)"
        ));
        assert!(!has_gpu(
            "Available devices:\n  Vulkan0: llvmpipe (8192 MiB, 7000 MiB free)"
        ));
        assert!(!has_gpu("Available devices:\n  (none)"));
    }
}
