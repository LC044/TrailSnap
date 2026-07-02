### 第一步：安装Docker Desktop
Docker Compose已经集成在Docker Desktop中，所以先安装它：
1. 访问Docker官网下载：https://www.docker.com/products/docker-desktop/
2. 双击下载的安装包，一路点击「Next」（勾选「Use WSL 2 instead of Hyper-V」）
3. 安装完成后，重启一下电脑
4. 启动Docker Desktop（首次启动可能需要几分钟，右下角会显示Docker图标）
5. 如果是第一次使用，启动之后会弹出一个黑框，提示你下载“适用于 Linux 的 Windows 子系统”，根据要求下载即可
6. 配置加速器：打开setting->Docker Engine，写入以下内容：
   ```json
   {
     "builder": {
       "gc": {
         "defaultKeepStorage": "20GB",
         "enabled": true
       }
     },
     "experimental": false,
     "registry-mirrors": ["https://docker.1ms.run"]
   }
   ```
   点击「Apply & Restart」，重启Docker Desktop。

7. 验证安装：按下`Win + R`，输入`cmd`打开命令提示符，执行：
   ```bash
   docker --version
   docker-compose --version
   ```
   如果能显示版本号，说明安装成功。

### 第二步：准备docker-compose.yml文件
1. 新建一个空白文件夹，例如`D:\TrailSnap`
2. 在文件夹中新建一个文件，命名为`docker-compose.yml`
3. 用文本编辑器打开`docker-compose.yml`文件，复制粘贴以下内容：


```yaml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg18-trixie
    container_name: postgres_container
    restart: always
    environment:
      POSTGRES_DB: trailsnap
      POSTGRES_USER: trailsnap
      POSTGRES_PASSWORD: trailsnap
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --lc-collate=C --lc-ctype=C"
      PGDATA: /var/lib/postgresql/data/pgdata
    networks: [ app-network ]
    volumes:
      - ./pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trailsnap -d trailsnap -p 5432"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  server:
    image: siyuan044/trailsnap-server:latest
    restart: always
    expose: [ "8000" ]
    ports: [ "8800:8000" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data
      - ./photos:/app/Photos
    environment:
      - DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/trailsnap
      - RAILWAY_DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/railway
      - AI_API_URL=http://ai:8001
    depends_on:
      postgres:
        condition: service_healthy

  ai:
    image: siyuan044/trailsnap-ai:latest
    restart: always
    expose: [ "8001" ]
    ports: [ "8801:8001" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data

  frontend:
    image: siyuan044/trailsnap-frontend:latest
    restart: always
    ports: [ "8082:80" ]
    depends_on: [ server ]
    networks: [ app-network ]

networks:
  app-network:
    driver: bridge
```


修改文件挂载目录：
找到`docker-compose.yml`文件中`server`的`volumes`配置，修改挂载目录`./photos:/app/Photos`为你自己的照片目录。
例如，我的照片目录是`D:\TrailSnap\photos`，则修改为：

```yml
  server:
    image: siyuan044/trailsnap-server:latest
    restart: always
    expose: [ "8000" ]
    ports: [ "8800:8000" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data
      - D:\TrailSnap\photos:/app/Photos
    environment:
      - DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/trailsnap
      - RAILWAY_DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/railway
      - AI_API_URL=http://ai:8001
    depends_on:
      postgres:
        condition: service_healthy
```

如果你有多个照片目录，例如`D:\TrailSnap\photos1`、`D:\TrailSnap\photos2`，则可以在`docker-compose.yml`中添加多个挂载目录：

```yml
  server:
    image: siyuan044/trailsnap-server:latest
    restart: always
    expose: [ "8000" ]
    ports: [ "8800:8000" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data
      - D:\TrailSnap\photos:/app/Photos
      - D:\TrailSnap\photos1:/app/Photos1
      - D:\TrailSnap\photos2:/app/Photos2
```
冒号前面是本地目录，冒号后面是TrailSnap用到的目录。

### 第三步：执行部署命令
1. 打开命令提示符（`Win + R` → `cmd`），切换到`docker-compose.yml`所在的文件夹：
   ```bash
   # 示例：如果文件在D盘的TrailSnap文件夹，执行
   cd /d D:\TrailSnap
   ```
2. 启动服务（核心命令）：
   ```bash
   docker-compose up -d
   ```
   - `up`：启动配置文件中的所有服务
   - `-d`：后台运行（不占用当前命令行窗口）
3. 等待执行完成：Docker会自动下载所需的镜像、创建容器并启动服务、完成之后显示以下内容：

```bash
PS C:\ProgramData\TrailSnap> docker-compose up -d
time="2026-03-06T17:42:03+08:00" level=warning msg="C:\\ProgramData\\TrailSnap\\docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
[+] up 51/51
 ✔ Image siyuan044/trailsnap-frontend:latest Pulled                                                               38.2ss
 ✔ Image siyuan044/trailsnap-ai:latest       Pulled                                                               155.8s
 ✔ Image pgvector/pgvector:pg18-trixie       Pulled                                                               76.8ss
 ✔ Image siyuan044/trailsnap-server:latest   Pulled                                                               112.8s
 ✔ Network trailsnap_app-network             Created                                                              0.1s
 ✔ Container postgres_container              Healthy                                                              28.0s
 ✔ Container trailsnap-ai-1                  Created                                                              1.1s
 ✔ Container trailsnap-server-1              Created                                                              0.1s
 ✔ Container trailsnap-frontend-1            Created                                                              0.1s
```

### 第四步：验证部署是否成功

打开浏览器，访问`http://localhost:8082`，即可看到TrailSnap的前端界面。

然后点击更多->设置->外部图库，添加`/app/Photos`。
如果有多个照片目录，例如`/app/Photos1`、`/app/Photos2`，则可以添加多个。

### 常见问题解决
1. **启动时提示“找不到docker-compose.yml”**：确认命令行当前目录是文件所在目录，或执行`docker-compose -f 完整路径/文件名.yml up -d`。
2. **端口被占用**：查看`docker-compose.yml`中的`ports`配置（比如`8080:80`），修改前面的端口（如`8081:80`），再重新执行`docker-compose up -d`。

---

### 总结
1. **核心前提**：安装Docker Desktop并验证成功（`docker --version`）。
2. **关键步骤**：将`docker-compose.yml`放在单独文件夹，用`cd`切换到该目录，执行`docker-compose up -d`启动服务。
3. **验证/维护**：用`docker-compose ps`查看状态，`docker-compose logs`排查问题，`docker-compose down`停止并删除容器。