# 360° 全景照片（REQ-155 阶段一）

支持已拼接的等距柱状全景照片。导入时解析 XMP 的 GPano 投影、完整画布、裁剪区域和可选视角；普通 2:1 图片不会仅凭比例自动成为全景。完整及裁剪全景都需要有效的几何参数。阶段一以大疆导出的 JPEG 为实测样例，不包含视频、原始序列拼接、双鱼眼和厂商私有文件。

## 使用

- 图库筛选面板的“类型”分组中提供“360° 全景”，缩略图带有 360° 标识。
- 已有图库需要重新识别时，在现有任务管理中执行元数据提取／重建元数据，完成后刷新图库。不提供独立补识别入口。
- 灯箱默认以全景方式打开已识别照片，支持拖动、双指缩放、滚轮、重置、全屏和上一张／下一张。
- 查看器的全景图标只切换本次浏览方式，不修改照片的识别结果。重置视角、全屏和高清画质放在“更多”菜单中。手机端沿用单行底部操作栏。
- 查看器不提供手动全景标记。缺少有效 GPano 元数据的图片保留普通照片浏览；不能仅凭 2:1 比例确定球面投影。
- 默认遵循“自动查看原图”设置：开启时优先使用原始分辨率；关闭或设备不支持时使用完整球面画布不超过 4096 像素宽的标准预览。原始分辨率仍需满足设备纹理、内存和服务端 8192×4096 预算，可在本次查看中手动切换画质。失败时保留平面浏览。
- 原图不被改写；从图片编辑器替换图片时清除旧全景属性，避免裁剪或旋转后沿用失效投影。

## 数据及接口

`photos` 新增 `panorama_projection`、`panorama_metadata`、`panorama_detected`、`panorama_override`。保留早期字段的数据库兼容性；元数据重处理会清除早期人工覆盖并重新计算识别结果。PostgreSQL 和 SQLite 各有一个 Alembic 迁移。

浏览接口带应用 `/api` 前缀，均需要当前用户身份；只能读取自己的未删除图片。只读查询不加行锁，避免被后台处理事务阻塞：

| 接口 | 用途 |
| --- | --- |
| `GET /api/photos/{id}/panorama` | 投影、几何参数、识别来源及尺寸 |
| `GET /api/photos/{id}/panorama/image?high=false` | 鉴权的专用 JPEG 浏览资源，采用私有缓存策略 |

列表、详情列表和时间轴支持 `is_panorama=true/false`，与相机、截图等原有分类相互独立。结构化接口返回 `BaseResponse`；图片接口成功返回 JPEG，业务失败返回 `BaseResponse`。

## 验证

```powershell
pwsh .\tests\scripts\run-tests.ps1 -Layer unit -Component server -Level smoke -Scope photo
pwsh .\tests\scripts\run-tests.ps1 -Layer unit -Component server -Level smoke -Scope system
pwsh .\tests\scripts\run-tests.ps1 -Layer unit -Component website -Level smoke
```

照片模块包含解析、无元数据误判、人工覆盖、资源鉴权、预览尺寸、扫描任务和 PostgreSQL 迁移 SQL 生成用例；系统模块覆盖 SQLite 迁移到当前模型。前端测试覆盖纹理预算、裁剪缩放、过时响应、元数据／纹理加载超时及失败重试。加载设有整体超时并取消过期请求，容器不可用时退出加载状态。
