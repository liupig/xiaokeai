放角色模型（3D 人物）
====================

支持：.pmx（MMD）、.vrm、.glb
不要把 .pmx 的贴图拆丢，整夹一起放。

推荐结构：

  models/
    清宵/                 ← 一个角色一个文件夹（PMX 用文件夹名当角色名）
      清宵.pmx
      tex/                贴图
    someone.vrm           ← VRM / GLB 可以直接扔在这一层
    someone.glb

从哪里来：资产中心本地导入，或模之屋下载。不要提交进 git。

Put character models here (.pmx / .vrm / .glb). One folder per PMX. Do not commit them.
