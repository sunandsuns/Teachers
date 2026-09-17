import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** 统一的 Markdown 渲染组件，样式在 index.css 的 .markdown-body 定义。 */
export default function Markdown({ content }: { content: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}
