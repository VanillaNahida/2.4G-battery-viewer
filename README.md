# 设备电量监视器

Windows 上读取无线外设与蓝牙设备电量的托盘小工具：**PyQt-Fluent-Widgets 界面 + 多设备抽象层**，
支持 2.4G 无线鼠标/耳机、蓝牙耳机/键鼠/手柄，支持托盘多图标、低电量提醒与自定义提示音。

## 功能

- **设备卡片界面**：设备名、来源与型号、VID:PID 或蓝牙地址、电量（大号数字 + 进度条）、状态、更新时间。
- **深浅色 + 跟随系统**：Fluent 主题，可在设置里切换。
- **托盘常驻**：
  - 图标形态可切：**数字图标**（默认）/ **环形电量** / **纯图标**；
  - 多设备时**每个设备一个托盘图标**（可关）；
  - 悬停提示可关；左键单击 = 立即刷新，双击 = 打开主界面，右键 = 菜单。
- **低电量提醒**：Windows 通知 + 播放提示音（默认 `assets/notification-2.mp3`，可自选）；
  **每个设备可以单独设 启用开关 / 阈值 / 提示音**，并各自有冷却时间。
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

## 支持的设备

| 设备 | 识别方式 | 读取方式 |
|---|---|---|
| 英菲克 IN9（三模游戏鼠标） | 2.4G 接收器 `249A:5C2F` / `248A:5C2F` | 厂商 HID 协议：33 字节帧，命令 `0x00` 读状态，电量在应答第 14 字节 |
| ATK / VXE 无线鼠标 | `373B` / `3554` | Nordic 厂商协议（Report ID `0x08`），见 `hid/strategies.py` |
| DARKRIM SHADOW 耳机 | `3654:6901` | 杰理 JL_RCSP 私有 TLV 协议（CRC16-CCITT-FALSE） |
| 蓝牙耳机 / 音箱 / 键鼠 / 手柄 | BTHENUM / BTHLE 设备节点 | Windows 未公开 PnP 属性 `{104EA319-…},2`（由设备上报后驱动写入） |

两个注意点（都已如实处理，不猜）：

- **英菲克 IN9 的充电状态**：应答报文里没有充电位，只有设备主动上报的事件
  `00 c0 <充电标志> <电量> …` 才带充电信息。抓不到事件时界面显示"充电状态未知"。
- **蓝牙电量**：属性是缓存值，设备断开或不上报时会是 0 或不存在——此时显示
  "设备未连接或未上报电量"，**不会**当成 0%。

## 目录结构

```
device_battery/
├── __main__.py          入口（命令行 + 单实例 + 生命周期）
├── core/                路径 / 配置 / 开机自启 / 单实例
├── hid/                 hid_win.py（纯 ctypes HID 层）+ strategies.py（通用电量策略）
├── devices/             设备抽象：base.py + 各来源实现
│   ├── inphic_in9.py    英菲克 IN9
│   ├── atk_vxe.py       ATK / VXE
│   ├── darkrim.py       DARKRIM 耳机
│   └── bluetooth.py     蓝牙设备（0..N 个，按地址去重）
├── ui/                  Fluent 界面（主窗口 / 卡片 / 设置页 / 调试页 / 主题）
├── tray/                托盘图标渲染、托盘管理、读取调度
└── notify/              Windows 通知、提示音、按设备的预警状态机
```

设备抽象是「一个来源（Provider）枚举 0..N 个设备」——因为蓝牙设备是动态增删的。
主程序只用 `devices.scan_all()` 取全部设备读数，不关心具体来源怎么通信。
新增设备只需写一个 `devices/xxx.py` 并在 `devices/__init__.py` 里登记。

## 设置项

`config.json`（与旧版 `tray_config.json` 自动迁移）：

- `interval` 刷新间隔、`autostart` 开机自启、`theme` 主题、`quit_on_close` 关窗口是否退出、
  `show_absent_devices` 是否显示未检测到的设备；
- `tray.*` 图标形态 / 多图标 / 悬停提示 / 蓝牙是否上托盘；
- `notify.*` 总开关、全局阈值、提示音、音量、冷却时间；
- `notify.overrides` **每设备覆盖**（如 `{"inphic:in9": {"threshold": 30}}`）。

## 约定

- **不写任何日志文件**：只有 `--debug` 时才往控制台打印。
- **不联网**：没有 http / socket / 遥测调用。
- 开机自启用「启动」文件夹的快捷方式（任务管理器 ->「启动」可见）；
  常驻程序**只读**自启状态，绝不替用户改系统设置。
- 代码、界面、文档不使用 emoji。

## 说明

`PROMPT.md` 是旧版（纯 ctypes、零第三方依赖、Tk 界面）的可复用提示词，现作为历史保留。
私有协议部分通过逆向厂商软件与抓包分析得到，仅供学习与个人使用。
