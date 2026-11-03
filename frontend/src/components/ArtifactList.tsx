import { Download, FileText } from 'lucide-react';
import type { AgentFile } from '@personal-agent/sdk';

interface ArtifactListProps {
  artifacts: AgentFile[];
  onPreview: (file: AgentFile) => void;
  onDownload: (file: AgentFile) => void;
}

export function ArtifactList({ artifacts, onPreview, onDownload }: ArtifactListProps) {
  return (
    <div className="artifact-list">
      {artifacts.map((f) => (
        <div className="artifact" key={f.id}>
          <FileText size={24} />
          <button onClick={() => onPreview(f)}>
            <strong>{f.name}</strong>
            <small>Markdown 产物 · {(f.size / 1024).toFixed(1)} KB · 点击预览</small>
          </button>
          <button
            className="icon-button"
            aria-label={`下载 ${f.name}`}
            onClick={() => onDownload(f)}
          >
            <Download size={17} />
          </button>
        </div>
      ))}
    </div>
  );
}
