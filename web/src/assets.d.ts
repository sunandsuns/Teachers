/**
 * 静态资源的模块声明。
 *
 * 这个项目此前没有这类声明——因为在那之前没往 `src/` 里放过图片，网络访问也
 * 一律收拢在 `api/`。现在「画像」的形象是两页真实的册页（`src/assets/*.webp`），
 * TS 不认识这个后缀，所以补一条。
 *
 * 只声明**用得上的那一种**，不整包引 `vite/client` 的类型：那个声明面覆盖
 * 环境变量、HMR 等一大堆本项目用不到的东西，扩进来容易和现有 `tsconfig`
 * 的严格配置打架。以后要放别的图，在这里照样加一条即可。
 */
declare module '*.webp' {
  const src: string
  export default src
}
