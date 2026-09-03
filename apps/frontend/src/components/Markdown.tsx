/**
 * Minimal, safe Markdown renderer.
 *
 * Builds React nodes directly from text (never dangerouslySetInnerHTML), so
 * there is no HTML-injection risk. Supports the subset models actually emit:
 * headings (#/##/###), bold **…**, italic *…*, inline `code`, bullet and
 * numbered lists, and paragraphs. Anything else falls through as plain text.
 */
import { Fragment, ReactNode } from "react";

const INLINE = /(\*\*([^*]+)\*\*|`([^`]+)`|\*([^*\n]+)\*)/g;

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  INLINE.lastIndex = 0;
  while ((m = INLINE.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[2] !== undefined) nodes.push(<strong key={key++}>{m[2]}</strong>);
    else if (m[3] !== undefined) nodes.push(<code key={key++}>{m[3]}</code>);
    else if (m[4] !== undefined) nodes.push(<em key={key++}>{m[4]}</em>);
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export default function Markdown({ text }: { text: string }) {
  const lines = (text || "").split("\n");
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let key = 0;

  const flushList = () => {
    if (!list) return;
    const items = list.items.map((it, i) => <li key={i}>{renderInline(it)}</li>);
    blocks.push(list.ordered ? <ol key={key++}>{items}</ol> : <ul key={key++}>{items}</ul>);
    list = null;
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    const heading = line.match(/^(#{1,3})\s+(.*)$/);

    if (bullet) {
      if (!list || list.ordered) {
        flushList();
        list = { ordered: false, items: [] };
      }
      list.items.push(bullet[1]);
      continue;
    }
    if (numbered) {
      if (!list || !list.ordered) {
        flushList();
        list = { ordered: true, items: [] };
      }
      list.items.push(numbered[1]);
      continue;
    }
    flushList();
    if (heading) {
      const level = heading[1].length;
      const content = renderInline(heading[2]);
      blocks.push(
        level === 1 ? (
          <h3 key={key++} className="md-h">{content}</h3>
        ) : level === 2 ? (
          <h4 key={key++} className="md-h">{content}</h4>
        ) : (
          <h5 key={key++} className="md-h">{content}</h5>
        ),
      );
      continue;
    }
    if (line.trim() === "") {
      blocks.push(<div key={key++} className="md-gap" />);
      continue;
    }
    blocks.push(
      <p key={key++} className="md-p">
        {renderInline(line)}
      </p>,
    );
  }
  flushList();

  return <div className="md">{blocks.map((b, i) => <Fragment key={i}>{b}</Fragment>)}</div>;
}
