# 项目 Logo

唯一资源目录：`frontend/public/branding/`，仅保留原始黑色和七款新增配色。
所有图片保留确认模板的尺寸、透明度和白色轮廓；配色不重绘形状。

统一修改入口是该目录下的 `brand.json`。将 `defaultLogo` 改成其中一个键即可切换默认款，当前为 `jd-red`。开发服务重新启动、桌面应用重新启动后生效，发行包需重新构建。

Vue 页面用 `components/BrandLogo.vue`，例如 `<BrandLogo :size="24" />`；需要 URL 时用 `branding.ts` 的 `getLogoUrl()`。传入配色键可获取指定版本。

Electron 用 `desktop/branding.js` 的 `getLogoPath()`；窗口和托盘共用它。打包脚本会将同一资源目录复制到桌面发行包，启动器图标也从该配置生成。

如需更换图案或调整配色，直接替换对应 PNG 即可。不要在调用处复制图片或写死颜色文件名。
