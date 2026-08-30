# 设置外部图库

添加外部文件夹路径，系统将扫描这些文件夹中的图片。外部文件夹中的图片不会被移动或修改，生成的缩略图将存储在主目录中。

查看docker-compose.yml文件，确认photos文件夹的挂载路径。

```yml
  server:
    image: crpi-d7wuvvdylhqugyu2.cn-hangzhou.personal.cr.aliyuncs.com/siyuan044/trailsnap-server:latest
    restart: always
    expose: [ "8000" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data
      - D:\TrailSnap\photos:/app/Photos/
```

冒号前面是电脑上的文件夹路径，冒号后面是容器内的路径。外部图库要添加的目录为冒号后面的路径，也就是`/app/Photos/`。

你也可以挂载多个文件夹，只需要在volumes中添加多个挂载路径即可。修改之后要重启docker容器，使配置生效。

```yml
      - D:\TrailSnap\photos1:/app/Photos1/
      - E:\TrailSnap\photos2:/app/Photos2/
```

也可以添加外部文件夹的某个子文件夹，例如只想添加`D:\TrailSnap\photos1\2025\`中的图片，那么外部图库为`/app/Photos1/2025/`。
