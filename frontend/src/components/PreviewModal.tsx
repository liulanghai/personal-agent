import { FileText, X } from 'lucide-react';
import Markdown from 'react-markdown';

export interface Preview {
  title: string;
  content: string;
}

export function PreviewModal({ preview, onClose }: { preview: Preview; onClose: () => void }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="preview-modal"
        role="dialog"
        aria-modal="true"
        aria-label={preview.title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <FileText size={18} />
          <strong>{preview.title}</strong>
          <button className="icon-button" aria-label="关闭预览" onClick={onClose}>
            <X size={19} />
          </button>
        </div>
        <div className="markdown-preview">
          <Markdown>{preview.content}</Markdown>
        </div>
      </section>
    </div>
  );
}
