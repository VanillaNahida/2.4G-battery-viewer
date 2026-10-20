# 设备电量监视器

Windows 上读取无线外设与蓝牙设备电量的托盘小工具：**PyQt-Fluent-Widgets 界面 + 多设备抽象层**，
支持 2.4G 无线鼠标/耳机/手柄、蓝牙耳机/键鼠/手柄，支持托盘多图标、低电量提醒与自定义提示音。

## 功能

- **设备卡片（只留必要信息）**：设备图标、设备名、状态（充电中 / 放电中 / 连接方式）、电量。
  - 电量显示方式可切：**环形电量（环内百分比）**，或**进度条 + 百分比**
    （进度条在卡片底部通栏，百分比在右侧）；
  - 顶部有**立即刷新**按钮，想马上读一次不用等定时器。
- **只显示真正连上的设备**：
  - 2.4G：只插着接收器、设备没开机时不会挂空卡片；
  - 蓝牙：Windows 会把「已配对」设备的电量属性一直留着（缓存值），
    所以这里额外用 `bthprops` 的 `fConnected` 判断连接状态，
    **已配对但没连上的设备不显示**；
  - 需要的话可在设置里打开「显示未检测到的设备」查看占位卡。
- **高 DPI 适配**：声明每屏 DPI 感知并打开 Qt 缩放，2K / 4K 屏幕上跟随系统缩放比例，不再又小又糊。
- **字体可换**：默认加载 `assets/fonts` 里的 **MiSans**；界面字体与托盘数字字体可以分别设置，
  也能「加载字体文件…」用任意 ttf/otf。
- **深浅色**：标题栏左侧（最小化按钮左边）有**一键切换按钮**，也可以在设置里选跟随系统。
- **电量配色可调**：电量低于「橙黄色阈值」（默认 30%）时环 / 数字转橙黄，
  低于「红色阈值」（默认 20%）转红，其余为绿；两个阈值都在设置 → 外观里改，
  卡片、环形、进度条、托盘图标一起生效。
- **托盘常驻**：
  - 图标形态可切：**数字图标**（默认）/ **环形电量** / **仅圆环** / **纯图标**，
    右键菜单「图标形态」里可以直接切换；
  - 环形电量的缺口是**透明**的（不再有深色底圈），数字尽量放大；
  - 多设备时**每个设备一个托盘图标**（可关）；
  - 悬停提示可关；左键单击 = 立即刷新，双击 = 打开主界面，右键 = 菜单。
- **低电量提醒**：只走 **Windows 系统通知**（托盘气泡 NIIF_INFO：info 图标 + 标题 + 内容，
  会进通知中心）+ 提示音（默认 `assets/notification-2.mp3`，可自选）；
  **每个设备可以单独设 启用开关 / 阈值 / 提示音**，并各自有冷却时间。
- **通知身份**：第一次发通知时会在开始菜单放一个带 AUMID 的快捷方式，
  这样「设置 → 系统 → 通知」里能看到「设备电量」并能单独开关它（删掉该快捷方式即可注销）。
- **通知文案与测试**：标题 / 正文是可编辑模板，支持魔法变量（`{name}` `{level_pct}`
  `{status}` `{time}` `{min_name}` …），设置页里能**直接发送一条测试通知**看效果。
- **调试页**：枚举 HID 接口、转储 Feature Report、监听原始报文。

## 环境与安装

需要 Windows 10/11 与 Python 3.10+。依赖用 [uv](https://docs.astral.sh/uv/) 管理：

```bash
uv sync          # 创建 .venv 并安装依赖（含本项目，可编辑安装）
```

依赖：`PyQt5`、`PyQt-Fluent-Widgets`、`winotify`。
底层 HID 与蓝牙枚举仍是**纯 ctypes、零第三方依赖**（见 `device_battery/hid/hid_win.py`
与 `device_battery/devices/bluetooth.py`）。

> 注意：`PyQt5-Qt5` 在 `pyproject.toml` 里钉在 `5.15.2`——更新的版本不再提供 Windows wheel。

## 用法

```bash
uv run python -m device_battery               # 启动（主窗口 + 托盘）
uv run python -m device_battery --minimized    # 只留托盘（开机自启用）
uv run python -m device_battery --once         # 命令行读一次，打印所有设备
uv run python -m device_battery --bluetooth    # 只列出蓝牙设备与电量
uv run python -m device_battery --status       # 配置 / 开机自启 / 是否已有实例在跑
uv run python -m device_battery --quit         # 让正在运行的实例退出
uv run python -m device_battery --debug        # 输出调试日志
```

也可以直接用控制台脚本：`uv run device-battery`。

## 打包成 exe

```bash
uv run python build_exe.py             # 单文件：dist/设备电量.exe（默认）
uv run python build_exe.py --onedir    # 目录版：dist/设备电量/设备电量.exe（启动更快）
uv run python build_exe.py --clean     # 打包前清掉 build/ 与 dist/
uv run python build_exe.py --console   # 带控制台，方便看报错
```

- 图标用 `assets/logo.ico`：既是 **exe 的内嵌图标**，也是**窗口 / 任务栏图标**；
  托盘图标仍由程序按电量实时绘制，不受影响；
- **版本资源**来自 `pyinstaller_version.txt`（`--version-file`）：资源管理器 → 属性 →
  详细信息里的**文件说明 / 版权 / 版本号**都由它决定；默认值对应 `2.0.0.0`，
  与 `pyproject.toml`、`device_battery.__version__` 不一致时打包脚本会打印提醒；
  也可用 `--version-file ""` 显式跳过；
- **只打包运行时真正用到的资源**（白名单）：
  `assets/fonts/*.ttf`（MiSans）、`assets/*.mp3`（提示音）、`assets/logo.ico`（图标）；
  其余素材（`logo.png`、`logo.svg`、`键鼠.png`、设计稿 PNG…）不会进 exe，
  打包时会把「已打包 / 已跳过」的文件清单打印出来；
- `config.json` **不打进去**，首次运行生成在 **exe 同目录**（`paths.py` 会区分
  「可写根 = exe 目录」和「只读资源根 = 解包目录」）；
- 打包后开机自启、通知身份的快捷方式会自动指向 exe 本身（不再是 `pythonw -m device_battery`）；
- 需要 PyInstaller，脚本会自动安装（优先 `pip`，其次 `uv pip`）。

## 支持的设备

| 设备 | 识别方式 | 读取方式 |
|---|---|---|
| 英菲克 IN9（三模游戏鼠标） | 2.4G 接收器 `249A:5C2F` / `248A:5C2F` | 厂商 HID 协议：33 字节帧，命令 `0x00` 读状态，电量在应答第 14 字节 |
| ATK / VXE 无线鼠标 | `373B` / `3554` | Nordic 厂商协议（Report ID `0x08`），见 `hid/strategies.py` |
| DARKRIM SHADOW 耳机 | `3654:6901` | 杰理 JL_RCSP 私有 TLV 协议（CRC16-CCITT-FALSE） |
| 墨将凌云（BIGBIG WON）手柄 | 厂商集合 `413D:2104`（UsagePage `0xFF7A`，65 字节报文） | 墨将厂商 HID 协议：`A5 04 04 AD` 读电量，应答 `A5 06 04 <电量%> <标志> <校验>`；2.4G 与有线连接共用同一套协议 |
| 蓝牙耳机 / 音箱 / 键鼠 / 手柄 | BTHENUM / BTHLE 设备节点 | Windows 未公开 PnP 属性 `{104EA319-…},2`（由设备上报后驱动写入） |

两个注意点（都已如实处理，不猜）：

- **英菲克 IN9 的充电状态**：应答报文里没有充电位，只有设备主动上报的事件
  `00 c0 <充电标志> <电量> …` 才带充电信息。抓不到事件时界面显示"充电状态未知"。
- **墨将凌云的充电状态**：电量应答里第 6 个字节（标志位）观测恒为 `0x00`，含义没有确认，
  所以不把它当充电标志，界面显示"充电状态未知"。电量本身是手柄应答里直接给的百分比。
- **蓝牙电量**：属性是缓存值，设备断开或不上报时会是 0 或不存在——此时显示
  "设备未连接或未上报电量"，**不会**当成 0%。

## 目录结构

```
device_battery/
├── __main__.py          入口（命令行 + 单实例 + 生命周期）
├── core/                路径 / 配置 / 高 DPI / 字体 / 开机自启 / 单实例
├── hid/                 hid_win.py（纯 ctypes HID 层）+ strategies.py（通用电量策略）
├── devices/             设备抽象：base.py + 各来源实现
│   ├── inphic_in9.py    英菲克 IN9
│   ├── atk_vxe.py       ATK / VXE
│   ├── darkrim.py       DARKRIM 耳机
│   ├── bbw_lingyun.py   墨将凌云 手柄
│   └── bluetooth.py     蓝牙设备（0..N 个，按地址去重）
├── ui/                  Fluent 界面（主窗口 / 卡片 / 设置页 / 调试页 / 主题 / 自绘控件）
├── tray/                托盘图标渲染、托盘管理、读取调度
└── notify/              Windows 通知、提示音、通知模板、按设备的预警状态机
```

设备抽象是「一个来源（Provider）枚举 0..N 个设备」——因为蓝牙设备是动态增删的。
主程序只用 `devices.scan_all()` 取全部设备读数，不关心具体来源怎么通信。
新增设备只需写一个 `devices/xxx.py` 并在 `devices/__init__.py` 里登记。

界面只显示「在线且读到电量」的设备；`Reading.online` 表示**设备真的在回应**，
不是「接收器插着」。例如 DARKRIM 耳机没开机时 dongle 仍然枚举得到，
但读不到电量，此时该来源返回 `online=False`，主界面和托盘都不会挂空图标。

蓝牙更麻烦一点：Windows 对「已配对」的设备会一直保留电量属性（旧的缓存值），
所以 `devices/bluetooth.py` 另外调用 `bthprops` 的 `BluetoothFindFirstDevice`
读取 `fConnected`，只把**当前真的连着**的设备报上来。

## 设置项

`config.json`（与旧版 `tray_config.json` 自动迁移，坏值会回退默认值）：

- `interval` 刷新间隔、`autostart` 开机自启、`theme` 主题、`quit_on_close` 关窗口是否退出、
  `show_absent_devices` 是否显示未检测到的设备；
- `ui.font` 界面字体（默认 `MiSans`，空字符串 = 系统默认）、
  `ui.battery_style` 主界面电量显示（`ring` 环形内嵌百分比 / `bar` 进度条）；
- `colors.orange_at` / `colors.red_at` 变色阈值（默认 30 / 20，会自动纠正成 红 < 橙）；
- `fonts.extra_files` 用户「加载字体文件…」加入的字体路径（启动时自动注册）；
- `tray.*` 图标形态（`number` / `ring` / `ring_only` / `icon`）/ 托盘字体 / 多图标 / 悬停提示 / 蓝牙是否上托盘；
- `notify.*` 总开关、全局阈值、提示音、音量、冷却时间、
  通知文案 `title_template` / `body_template`；
- `notify.overrides` **每设备覆盖**（如 `{"inphic:in9": {"threshold": 30}}`）。

### 通知模板的魔法变量

| 变量 | 含义 | 变量 | 含义 |
|---|---|---|---|
| `{name}` | 设备名 | `{level}` | 电量数字（不含 %） |
| `{level_pct}` | 电量带 % | `{status}` | 充电中 / 放电中 / 充电状态未知 |
| `{charging}` | 充电 / 未充电 / 未知 | `{kind}` | 鼠标 / 键盘 / 耳机 / 手柄 |
| `{source}` | 数据来源 | `{transport}` | 2.4G / USB / Bluetooth |
| `{vid_pid}` | VID:PID 或蓝牙地址 | `{threshold}` | 该设备的低电量阈值 |
| `{time}` / `{date}` | 当前时间 / 日期 | `{count}` | 当前设备数 |
| `{min_name}` / `{min_level}` | 电量最低的设备名 / 电量 | `{app}` | 程序名 |

写错的变量不会被吞掉，而是原样显示，设置页也会提示「认不出的变量」。

## 约定

- **不写任何日志文件**：只有 `--debug` 时才往控制台打印。
- **不联网**：没有 http / socket / 遥测调用。
- 开机自启用「启动」文件夹的快捷方式（任务管理器 ->「启动」可见）；
  常驻程序**只读**自启状态，绝不替用户改系统设置。
- 代码、界面、文档不使用 emoji。

## 说明

`PROMPT.md` 是旧版（纯 ctypes、零第三方依赖、Tk 界面）的可复用提示词，现作为历史保留。
私有协议部分通过逆向厂商软件与抓包分析得到，仅供学习与个人使用。
