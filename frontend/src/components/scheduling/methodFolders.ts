export interface MethodItem { id: string; name: string; path: string }
export interface MethodFolder { key: string; name: string; path: string; children: MethodFolder[]; direct: number }
export const REVIEW_FOLDER = '!review';
export function pathParts(raw: string): string[] | null {
  const path = raw.replace(/\//g, '\\');
  const drive = path.match(/^([a-z]:)\\/i);
  const unc = path.match(/^(\\\\[^\\]+\\[^\\]+)\\/);
  const root = drive?.[1] || unc?.[1];
  if (!root) return null;
  const parts = path.slice(root.length + 1).split('\\').filter(Boolean);
  if (!parts.length || parts.some(part => part === '.' || part === '..')) return null;
  return [root, ...parts];
}
export const folderKey = (path: string) => pathParts(path)?.slice(0, -1).join('\\').toLowerCase() || REVIEW_FOLDER;
export function inFolder(path: string, folder: string) {
  const key = folderKey(path);
  return folder === '*' || key === folder || (folder !== REVIEW_FOLDER && key.startsWith(folder + '\\'));
}
export function relativeMethodPath(path: string, folder: string) {
  const parts = pathParts(path);
  if (!parts || !folder || folder === '*' || folder === REVIEW_FOLDER) return path;
  return parts.join('\\').slice(folder.length + 1);
}
export function methodFolders(items: MethodItem[]): MethodFolder[] {
  const roots: MethodFolder[] = [];
  for (const item of items) {
    const parts = pathParts(item.path)?.slice(0, -1);
    if (!parts) continue;
    let siblings = roots;
    parts.forEach((name, index) => {
      const path = parts.slice(0, index + 1).join('\\');
      const key = path.toLowerCase();
      let node = siblings.find(node => node.key === key);
      if (!node) { node = { key, name, path, children: [], direct: 0 }; siblings.push(node); }
      if (index === parts.length - 1) node.direct += 1;
      siblings = node.children;
    });
  }
  function compress(nodes: MethodFolder[]): MethodFolder[] {
    return nodes.map(original => {
      let node = original;
      while (!node.direct && node.children.length === 1) node = node.children[0];
      return { ...node, children: compress(node.children) };
    }).sort((a, b) => a.path.localeCompare(b.path));
  }
  const result = compress(roots);
  if (items.some(item => !pathParts(item.path))) result.push({key: REVIEW_FOLDER, name: 'Needs path review', path: 'Needs path review', children: [], direct: 0});
  return result;
}
