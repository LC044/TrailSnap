## 目标

查一下去年国庆节去了哪些地方？帮我生成一个旅游日记。

## 步骤

1. 查询足迹时间轴，筛选出去年国庆节的地点。

```bash
trailsnap locations timeline --start-date "2025-10-01" --end-date "2025-10-07"
```

输出：

```json
[
  {
    "startDate": "2025-10-07",
    "endDate": "2025-10-07",
    "locationName": "上海市",
    "count": 7
  },
  {
    "startDate": "2025-10-05",
    "endDate": "2025-10-06",
    "locationName": "舟山市",
    "count": 133
  },
  {
    "startDate": "2025-10-05",
    "endDate": "2025-10-05",
    "locationName": "宁波市",
    "count": 8
  },
  {
    "startDate": "2025-10-04",
    "endDate": "2025-10-05",
    "locationName": "金华市",
    "count": 25
  },
  {
    "startDate": "2025-10-04",
    "endDate": "2025-10-04",
    "locationName": "衢州市",
    "count": 4
  },
  {
    "startDate": "2025-10-03",
    "endDate": "2025-10-03",
    "locationName": "景德镇市",
    "count": 28
  },
  {
    "startDate": "2025-10-02",
    "endDate": "2025-10-02",
    "locationName": "黄山市",
    "count": 152
  },
  {
    "startDate": "2025-10-02",
    "endDate": "2025-10-02",
    "locationName": "徽州古城景区",
    "count": 22
  },
  {
    "startDate": "2025-10-01",
    "endDate": "2025-10-01",
    "locationName": "湖州市",
    "count": 1
  },
  {
    "startDate": "2025-10-01",
    "endDate": "2025-10-01",
    "locationName": "苏州市",
    "count": 9
  },
  {
    "startDate": "2025-10-01",
    "endDate": "2025-10-01",
    "locationName": "苏州园林景区",
    "count": 43
  }
]
```

2. 根据足迹时间轴确定旅游日记的大致布局，生成旅游日记的大概框架。

3. 根据大纲，找到某一部分的照片，例如：2025年10月1日在苏州市的照片。

```bash
trailsnap photos list --city "苏州市" --limit 50
```

4. 查看某些值得记录到日记里照片的详细信息。

```bash
trailsnap photos info --photo-id <photo_id>
```

5. 根据要求查看对应照片的详细信息，进而生成旅游日记。

6. 获取某张照片的URL地址，将URL地址添加到旅游日记中。

```bash
trailsnap medias get --photo-id <photo_id> --format url --size medium
```
