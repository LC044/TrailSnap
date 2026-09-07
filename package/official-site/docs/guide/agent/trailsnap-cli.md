---
outline: [2, 3]
---


# TrailSnap CLI 工具

::: tip
TrailSnap CLI 工具是一个基于TrailSnap API的命令行工具，可以通过命令行管理TrailSnap的相册数据。
:::

## 一、安装使用

### 安装 trailsnap-cli工具

你可以通过以下三种方式下载安装trailsnap-cli工具：

1. pip 安装

```bash
pip install trailsnap-cli

# 验证安装是否成功
trailsnap -v
```

2. npm 安装

```bash
npm install -g trailsnap-cli

# 验证安装是否成功
trailsnap -v
```

3. 从GitHub获取二进制文件

从GitHub获取二进制文件，然后添加到环境变量中。
下载地址：[https://github.com/LC044/TrailSnap/releases](https://github.com/LC044/TrailSnap/releases)

### 使用 trailsnap-cli工具

首次使用需要配置TrailSnap的API URL和Token（替换 `<url>` 和 `<token>` 为实际的URL和Token，如何获取请参考[Token 设置](/docs/guide/settings/tokensetting)）。

```bash
trailsnap config set --url <url> --token <token>
```

配置完成之后使用简单查询命令验证是否成功。

```bash
trailsnap photos list --limit 5
```

## 二、命令列表

::: tip
核心说明：所有命令需在终端执行，格式统一为 `trailsnap <command> <subcommand> [options]`。涉及 API 交互的命令（如 photos、locations 等）需先通过 `config set` 配置 API 地址和 Token，否则会直接报错并退出。
:::

### 2.1、基础命令

#### 2.1.1 help - 显示帮助信息

「功能」：显示所有可用命令、命令结构及各命令的核心参数，快速查阅命令用法。
「格式」：`--help`
「示例」：
```bash
trailsnap --help
```

### 2.2、配置命令

#### 2.2.1 config set - 配置API URL和Token

「功能」：配置 CLI 使用的 TrailSnap 统一访问地址和 Bearer Token，是所有 API 交互类命令的前置操作。

「格式」：`config set --url API地址 --token API凭证`

「参数说明」：

- `--url`（必填）：TrailSnap 统一访问地址，例如：`http://localhost:3180`。CLI 会自动使用 `/api`。

- `--token`（必填）：API访问凭证（Bearer Token），用于身份验证，需从后端获取。

「示例」：

```bash
trailsnap config set --url http://localhost:3180 --token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

「输出说明」：配置成功后会输出配置文件保存路径（写入同目录 `.env`），例如：`配置已保存到 .../.env`。

### 2.3、照片管理命令

#### 2.3.1 photos - 照片管理主命令

「功能」：包含照片列表查询、单张照片详情获取、照片删除三个核心子命令，所有子命令需先完成API配置。

##### 2.3.1.1 photos list - 查询照片列表

「功能」：查询照片列表，支持分页与按相册/地点/设备信息过滤。返回结果为简化字段集合。

「格式」：`photos list [--skip N] [--limit N] [--album-id 相册ID] [--city 城市] [--province 省份] [--make 品牌] [--model 型号]`

「参数说明」（支持组合筛选）：

- `--skip`：跳过 N 张照片（默认 0）
- `--limit`：限制返回 N 张照片（默认 10）
- `--order_by`：排序字段，默认按值得回忆评分排序，可选值：quality_score（画面质量评分）,memory_score（值得回忆评分）,photo_time（拍摄时间）
- `--image-type`：按图片类型过滤照片，多个类型用逗号分隔，可选值：Camera（手机或相机拍摄）、Screenshot（截图）、Other（未知的其他类型）
- `--start-time`：按开始时间过滤照片，格式为 YYYY-MM-DD HH:MM:SS
- `--end-time`：按结束时间过滤照片，格式为 YYYY-MM-DD HH:MM:SS
- `--album-id`：按相册 ID 过滤，多个 ID 用逗号分隔
- `--people-id`：按人物 ID 过滤，多个 ID 用逗号分隔
- `--tag-id`：按标签 ID 过滤，多个 ID 用逗号分隔
- `--city`：按城市过滤，多个城市用逗号分隔（全称）
- `--province`：按省份过滤，多个省份用逗号分隔（全称）
- `--scene`：按景区过滤，多个景区用逗号分隔
- `--make`：按相机品牌过滤，多个品牌用逗号分隔
- `--model`：按相机型号过滤，多个型号用逗号分隔

「返回值」：JSON 数组，每项包含 `id`、`filename`、`file_type`、`photo_time`

「示例」：

```bash
trailsnap photos list --limit 20 --city 西安市,上海市
```

##### 2.3.1.2 photos info - 获取单张照片信息

「功能」：获取指定 ID 照片的元数据信息与内容描述信息。

「格式」：`photos info --photo-id 照片ID`

「参数说明」：

- `--photo-id`（必填）：照片唯一ID，可通过photos list命令获取。

「返回值」：JSON 对象，包含：

- `address`：照片详细拍摄地址（精确到街道）
- `albums`：所属相册信息
- `tags`：标签信息
- `faces_identities`：人物（面部识别身份）信息
- `description`：照片内容描述信息
  - `description`：照片画面描述（若无则为空字符串）
  - `memory_score`：照片值得回忆分数（0-100，100为值得回忆）
  - `quality_score`：照片质量分数（0-100，100为最高质量）
  - `narrative`：照片一句话文案（若无则为空字符串）

「示例」：

```bash
trailsnap photos info --photo-id 10001
```

##### 2.3.1.3 photos delete - 删除单张照片

「功能」：删除指定ID的照片，删除后不可恢复（需谨慎操作）。

「格式」：`photos delete --photo-id 照片ID`

「参数说明」：

- `--photo-id`（必填）：需删除的照片唯一ID。

「示例」：

```bash
trailsnap photos delete --photo-id 10001
```

「输出说明」：删除成功提示 `照片 <photo-id> 删除成功`，失败提示 `照片删除失败或不存在`。

### 2.4、分类标签命令

#### 2.4.1 tags list - 查询分类标签

「功能」：查询分类标签列表，支持分页。

「格式」：`tags list [--skip N] [--limit N]`

「参数说明」：

- `--skip`：跳过 N 个记录（默认 0）
- `--limit`：限制返回 N 个记录（默认 100）

「示例」：

```bash
trailsnap tags list
```

「输出说明」：输出 JSON 数组，每项包含 `id`、`name`（tag_name）、`count`。

### 2.5、相册管理命令

#### 2.5.1 albums list - 查询相册列表

「功能」：查询相册列表，支持分页。

「格式」：`albums list [--skip N] [--limit N]`

「参数说明」：

- `--skip`：跳过 N 个相册（默认 0）
- `--limit`：限制返回 N 个相册（默认 100）

「输出说明」：输出 JSON 数组，每项包含 `id`、`name`、`count`（num_photos）、`description`、`condition`、`type`。

「示例」：

```bash
trailsnap albums list
```

### 2.6、位置相关命令

#### 2.6.1 locations - 位置查询主命令

「功能」：包含位置分布查询、足迹时间轴查询两个子命令，基于照片的GPS信息统计。

##### 2.6.1.1 locations list - 查询位置分布

「功能」：查询位置分布，不含时间信息（地点名、照片数量）。支持按层级分组与日期范围过滤。

「格式」：`locations list [--level city|province|district|scene] [--skip N] [--limit N] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]`

「参数说明」：

- `--level`：分组级别（默认 city，可选：city、province、district、scene）
- `--skip`：跳过 N 个位置（默认 0）
- `--limit`：限制返回 N 个位置（默认 100）
- `--start-date`：可选，开始日期（YYYY-MM-DD）
- `--end-date`：可选，结束日期（YYYY-MM-DD）

「返回值」：JSON 数组，每项包含 `name`、`count`

「示例」：

```bash
trailsnap locations list
```

##### 2.6.1.2 locations timeline - 查询足迹时间轴

「功能」：查询足迹时间轴列表，按时间段和地点分组（开始日期、结束日期、地点名、照片数量）。支持按层级分组与日期范围过滤。

「格式」：`locations timeline [--level city|province|district|scene] [--skip N] [--limit N] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]`

「参数说明」：

- `--level`：分组级别（默认 city，可选：city、province、district、scene）
- `--skip`：跳过 N 个位置（默认 0）
- `--limit`：限制返回 N 个位置（默认 100）
- `--start-date`：可选，开始日期（YYYY-MM-DD）
- `--end-date`：可选，结束日期（YYYY-MM-DD）

「返回值」：JSON 数组，每项包含 `startDate`、`endDate`、`locationName`、`count`

「示例」：

```bash
trailsnap locations timeline --level city --start-date 2025-01-01 --end-date 2025-06-30
```

### 2.7、人物识别命令

#### 2.7.1 people list - 查询已识别的人物/面孔

「功能」：查询人物（面部识别身份）列表，支持按类型过滤。

「格式」：`people list [--limit N] [--types named,unnamed,hidden]`

「参数说明」：

- `--limit`：返回的记录数（默认 100）
- `--types`：查询类型，逗号分隔，默认 `named`；可选值：`named`、`unnamed`、`hidden`

「输出说明」：输出 JSON 数组，每项包含 `id`、`name`（identity_name）、`tags`、`description`、`face_count`。

「示例」：

```bash
trailsnap people list
```

### 2.8、存储文件夹命令

#### 2.8.1 folders list - 查询挂载的存储文件夹列表

「功能」：查询系统中已挂载的存储目录信息。

「格式」：`folders list`

「输出说明」：直接输出后端接口返回的 JSON（字段结构以服务端为准）。

「示例」：

```bash
trailsnap folders list
```

### 2.9、媒体文件命令

#### 2.9.1 medias get - 获取照片的媒体文件或URL

「功能」：获取指定照片的媒体内容/访问地址，支持输出 URL、base64、或保存到本地文件。

「格式」：`medias get [--photo-id 照片ID] [--size small|medium|large] [--format url|base64|file] [--output 文件路径]`

「参数说明」：

- `--photo-id`：照片 ID（默认 100）
- `--size`：照片质量/尺寸（默认 medium，可选：small、medium、large）
- `--format`：输出格式（默认 url（可以把链接插入到HTML页面或者markdown文件），可选：url、base64、file）
- `--output`：输出文件路径（仅当 `--format file` 时必填）

「示例」：

```bash
# 输出 URL（large 输出原图URL，small/medium 输出缩略图URL）
trailsnap medias get --photo-id 10001 --format url --size large

# base64 输出（缩略图base64编码）
trailsnap medias get --photo-id 10001 --format base64 --size medium

# 保存到本地文件
trailsnap medias get --photo-id 10001 --format file --output .\photo_10001.jpg
```

### 2.10、注意事项

- 所有涉及 API 交互的命令（photos、locations、people 等），必须先执行 `config set` 配置 API URL 和 Token，否则会提示 `错误: API URL 和 Token 未配置，请先运行 'config' 命令。` 并退出。

- 所有命令可通过 `--help` 查询详细用法，若参数错误，会提示具体错误信息及正确格式。
