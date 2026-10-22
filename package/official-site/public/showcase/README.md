# 官网展示素材

日记、月相和票夹由官网原生组件渲染，使用固定示例内容，不连接用户图库。
断舍离仅更新当前浏览器界面，不上传选择或删除文件。

- 风景图片：Unsplash，原始来源记录在 `assets/credits.json`。
- 月面图片：NASA/JPL/USGS，PIA00405；月相由示意遮罩呈现，不代表实拍记录。
- 城市地图：沿用 TrailSnap 的城市地理数据与演示相册城市分布快照，只读展示。
- 足迹拼图：直接复用 `package/website/src/utils/mapPuzzle/` 的投影、按省自适应网格、照片分配与绘制算法。`province-geo.json` 和 `puzzle-sample.json` 为公开演示站只读快照；`puzzle-photos/` 是按省选取的照片缩略图。无照片地区保持空白，支持点击省份放大和返回全国。
- `showcase-data.json` 仅包含城市汇总与本地示例照片路径，不包含账号、令牌或乘客信息。
- `echarts.min.js` 沿用项目依赖的 ECharts 发行文件，许可见文件头。

首页的相册和 3D 足迹仍来自 demo.siyuan.ink。免点击登录依赖演示站部署新版前端，以及后端启用 `DEMO_MODE=true`；普通私有部署继续使用正常登录。
