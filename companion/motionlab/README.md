# 无头 Blender Mixamo → VMD 转换管线

独立的 Python 模块，不依赖 `frontend/src/engine/mixamo.ts` 或 `.xkmotion`。Blender 和插件只安装在项目 `tools/` 下，不写系统目录、不需要管理员权限，也不会打开 Blender 界面。

## 组成

- `install_blender_pipeline.py`：下载并安装 Blender 4.5 LTS、mmd_tools 和 OpenCC。
- `blender_convert.py`：主机侧入口，定位 Blender 并启动无头进程。
- `blender_pipeline/cli.py`：目录批处理、失败汇总、输出检查。
- `blender_pipeline/config.py`：Mixamo 到 MMD 的 51 根骨骼映射，包含完整手指。
- `blender_pipeline/retarget.py`：双参考轴 rest pose 对齐、四元数重定向、按腿长缩放髋部、关键帧生成和 VMD 导出。

## 安装与检查

在 `companion/` 下执行：

```bash
python motionlab/install_blender_pipeline.py
python motionlab/install_blender_pipeline.py --check
```

本次已安装版本：Blender 4.5.16 LTS、mmd_tools 4.5.14。也可用 `BLENDER_BIN` 或入口的 `--blender` 指定其他 Blender。

## 转换

单文件：

```bash
python motionlab/blender_convert.py \
  --model assets/models/qingxiao/model.pmx \
  --output motionlab/out/blender-vmd \
  ../_dl/mixamo-dataset/animation_motion/Waving.fbx
```

整个目录：

```bash
python motionlab/blender_convert.py \
  --model assets/models/qingxiao/model.pmx \
  --output motionlab/out/blender-vmd \
  ../_dl/mixamo-dataset/animation_motion \
  --recursive
```

- 默认删除髋部水平位移，原地播放；`--allow-root-motion` 保留。
- `--limit 10` 限制目录转换数量，适合先抽样。
- 默认失败后继续；`--fail-fast` 在首个失败停止。
- 输出结束打印 `XIAOKE_CONVERSION_SUMMARY`，包含每个文件的帧数、映射骨骼数和错误。
- 把生成的 `.vmd` 放进 `assets/motions/`，再调用资产中心刷新或 `/api/assets/rescan`。

## 数据集

样本来自 [Linzhan/Mixamo-Animations-Characters](https://hf-mirror.com/datasets/Linzhan/Mixamo-Animations-Characters)。本次下载并验证了 `Waving`、`Walking`、`Jab_Cross`，也已批量转换最初的 5 个 FBX。

完整动作目录可另行克隆；动作很多，建议先用单文件或 `--limit`，不要未经抽检直接批量发布：

```bash
git clone https://hf-mirror.com/datasets/Linzhan/Mixamo-Animations-Characters
```

Mixamo 内容仍受 Adobe 条款约束。不要把原始 FBX 当成独立资产重新分发；发布包的动作资源也应按对应许可处理。

## Excel 精选动作包

`build_mixamo_pack.py` 内置 22 个陪伴场景动作。它会读取 Excel 的“动作清单”表、匹配本地数据集、批量转换，并生成 `assets/motions/xiaokeai-mixamo/manifest.json`：

```bash
python motionlab/build_mixamo_pack.py \
  --xlsx "path/to/Mixamo动作分类清单_xiaokeai适用.xlsx" \
  --input "../_dl/Mixamo-Animations-Characters/animation_motion" \
  --offline
```

`--offline` 只读本地克隆，不发起下载。后端资产扫描支持 `assets/motions/` 下的独立动作包子目录。

## 全部推荐动态动作包

`build_mixamo_recommended.py` 转换 Excel 全部“推荐”动作。1156 个推荐项中，129 个静态 Pose 不在动态目录，实际输出 1027 个 VMD 到 `assets/motions/mixamo-recommended/`：

```bash
python motionlab/build_mixamo_recommended.py \
  --xlsx "path/to/Mixamo动作分类清单_xiaokeai适用.xlsx" \
  --workers 4
```

默认跳过已存在的 VMD，可以中断后继续跑。最多 4 个 Blender 进程并行。重定向算法更新后，加 `--overwrite` 覆盖旧文件。整包可用 `node motionlab/validate_mixamo_pack.mjs assets/motions/mixamo-recommended` 校验。

在应用“表情 / 动作 / 运镜 → 动作库”中选择分类后，点“下一个”连续播放，界面显示“当前序号 / 筛选后总数”。本次 1027 个 VMD 全部通过解析检查，坐姿长对话、深蹲、街舞和张望已做舞台抽检。

## 陪伴自然动作精选包

`build_companion_daily.py` 保留当前实际使用的 34 个正常陪伴动作到 `assets/motions/companion-daily/`，包括聊天、思考、感谢、看手机、喝水和张望；不包含武器、格斗、受击、硬核健身、杂技、病痛和夸张特技。另有 9 个调用中的动作保留在 `assets/motions/xiaokeai-mixamo/`，两个清单都只登记仍在使用的文件。

```bash
python motionlab/build_companion_daily.py \
  --xlsx "path/to/Mixamo动作分类清单_xiaokeai适用.xlsx" \
  --workers 4
```

保留的 34 个 VMD 均已通过 Three.js 解析检查，Sitting_Drinking 等已在舞台验证。

## 验证与边界

- 映射测试：`python -m pytest motionlab/test_blender_pipeline.py -q`
- 本次使用 mmd_tools 导出后，再用 Three.js 的 MMD parser 检查帧数、骨骼轨道和有限数值。
- Waving、Walking、Jab_Cross 已在小可爱 Three.js 舞台实际播放检查。
- 双参考轴约束骨骼方向和 roll；手掌与手指保留 MMD 模型自己的自然手型，不播放 Mixamo 的独立手腕/手指旋转，避免不同绑骨和权重造成反折。
- 当前没有脚部 IK 或自动接地；极端身高比例、滑步、复杂位移舞蹈需要单独处理。
- 批量生成不等于批量质量合格。建议每批先抽样挥手、走路、出拳和转向，再跑全库。
