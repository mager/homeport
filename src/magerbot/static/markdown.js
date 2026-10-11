"use strict";
// Deliberately small Markdown renderer. All model content enters through textContent;
// no HTML parsing, remote images, embedded documents, or executable URL schemes.
window.HomeportMarkdown = (() => {
  function node(tag, text, className) {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (className) n.className = className;
    return n;
  }
  function safeURL(value) {
    try {
      const url = new URL(value);
      return ["https:", "http:", "mailto:"].includes(url.protocol) ? url.href : null;
    } catch { return null; }
  }
  function inline(parent, source, depth = 0) {
    if (depth > 4) { parent.append(document.createTextNode(source)); return; }
    const pattern = /`([^`\n]+)`|\*\*([^*\n]+)\*\*|\[([^\]\n]+)\]\(([^\s)]+)\)|\*([^*\n]+)\*/g;
    let start = 0;
    for (const match of source.matchAll(pattern)) {
      parent.append(document.createTextNode(source.slice(start, match.index)));
      if (match[1]) parent.append(node("code", match[1]));
      else if (match[2]) {
        const strong = node("strong"); inline(strong, match[2], depth + 1); parent.append(strong);
      } else if (match[3]) {
        const href = safeURL(match[4]);
        if (href) {
          const link = node("a"); link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer";
          inline(link, match[3], depth + 1); parent.append(link);
        } else parent.append(document.createTextNode(match[0]));
      } else {
        const emphasis = node("em"); inline(emphasis, match[5], depth + 1); parent.append(emphasis);
      }
      start = match.index + match[0].length;
    }
    parent.append(document.createTextNode(source.slice(start)));
  }
  function codeBlock(source, language) {
    const block = node("div", undefined, "code-block");
    const heading = node("div", undefined, "code-heading");
    const copy = node("button", "Copy", "copy-code");
    copy.type = "button"; copy.setAttribute("aria-label", "Copy code");
    copy.onclick = async () => {
      try {
        await navigator.clipboard.writeText(source);
        copy.textContent = "Copied";
      } catch { copy.textContent = "Select to copy"; }
      setTimeout(() => { if (copy.isConnected) copy.textContent = "Copy"; }, 2000);
    };
    heading.append(node("span", language || "code"), copy);
    const pre = node("pre", source); pre.tabIndex = 0;
    block.append(heading, pre);
    return block;
  }
  function render(source) {
    const root = node("div", undefined, "message-body");
    const lines = String(source || "").replace(/\r\n/g, "\n").split("\n");
    let index = 0;
    const boundary = (s) => /^\s*```|^#{1,6} |^\s*[-*] |^\s*\d+\. |^> ?/.test(s);
    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) { index++; continue; }
      if (/^\s*```/.test(line)) {
        const language = line.trim().slice(3).trim(); const code = [];
        index++;
        while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) code.push(lines[index++]);
        if (index < lines.length) index++;
        root.append(codeBlock(code.join("\n"), language));
      } else if (/^#{1,6} /.test(line)) {
        const h = node(/^#{1,2} /.test(line) ? "h3" : "h4");
        inline(h, line.replace(/^#{1,6} /, "")); root.append(h); index++;
      } else if (/^\s*(?:[-*]|\d+\.) /.test(line)) {
        const ordered = /^\s*\d+\. /.test(line);
        const list = node(ordered ? "ol" : "ul");
        if (ordered) list.start = parseInt(line.trim(), 10);
        const itemPattern = ordered ? /^\s*\d+\. / : /^\s*[-*] /;
        while (index < lines.length && itemPattern.test(lines[index])) {
          let text = lines[index++].replace(itemPattern, "");
          while (index < lines.length && /^\s+\S/.test(lines[index]) && !boundary(lines[index])) text += "\n" + lines[index++].trim();
          const li = node("li"); inline(li, text); list.append(li);
        }
        root.append(list);
      } else if (/^> ?/.test(line)) {
        const quote = node("blockquote"); const linesInQuote = [];
        while (index < lines.length && /^> ?/.test(lines[index])) linesInQuote.push(lines[index++].replace(/^> ?/, ""));
        inline(quote, linesInQuote.join("\n")); root.append(quote);
      } else {
        const paragraph = [lines[index++]];
        while (index < lines.length && lines[index].trim() && !boundary(lines[index])) paragraph.push(lines[index++]);
        const p = node("p"); inline(p, paragraph.join("\n")); root.append(p);
      }
    }
    return root;
  }
  return { render };
})();
