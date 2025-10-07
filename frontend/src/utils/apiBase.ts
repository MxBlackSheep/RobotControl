const stripTrailingSlash = (value: string): string => {
  if (value.length > 1 && value.endsWith('/')) {
    return value.slice(0, -1);
  }
  return value;
};

const ensureLeadingSlash = (value: string): string => {
  if (!value) {
    return '';
  }
  return value.startsWith('/') ? value : `/${value}`;
};

const LOCAL_DEV_HOSTS = new Set(['localhost', '127.0.0.1', '0.0.0.0']);

export const getApiBase = (): string => {
  const rawValue = (import.meta.env.VITE_API_BASE_URL ?? '').trim();
  if (!rawValue) {
    return '';
  }

  if (rawValue.startsWith('http://') || rawValue.startsWith('https://')) {
    try {
      const parsed = new URL(rawValue);

      if (typeof window !== 'undefined' && LOCAL_DEV_HOSTS.has(parsed.hostname)) {
        const runtimeHost = window.location.hostname || parsed.hostname;
        parsed.hostname = runtimeHost;
        parsed.host = parsed.port ? `${runtimeHost}:${parsed.port}` : runtimeHost;
      }

      if (parsed.pathname && parsed.pathname !== '/') {
        parsed.pathname = stripTrailingSlash(parsed.pathname);
      }

      const result = parsed.toString();
      const sanitized = stripTrailingSlash(result);
      return sanitized === '/' ? '' : sanitized;
    } catch (error) {
      const sanitized = stripTrailingSlash(rawValue);
      return sanitized === '/' ? '' : sanitized;
    }
  }

  const relative = stripTrailingSlash(ensureLeadingSlash(rawValue));
  return relative === '/' ? '' : relative;
};

const ensurePath = (path: string): string => (path.startsWith('/') ? path : `/${path}`);

export const buildApiUrl = (path: string): string => {
  const base = getApiBase();
  const normalizedPath = ensurePath(path);
  return `${base}${normalizedPath}`;
};

export const buildWsUrl = (path: string): string => {
  const normalizedPath = ensurePath(path);
  const apiBase = getApiBase();

  if (apiBase.startsWith('http://') || apiBase.startsWith('https://')) {
    const apiUrl = new URL(apiBase);
    const protocol = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:';
    const basePath = apiUrl.pathname.replace(/\/$/, '');
    return `${protocol}//${apiUrl.host}${basePath}${normalizedPath}`;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  const basePath = apiBase.replace(/\/$/, '');
  return `${protocol}//${host}${basePath}${normalizedPath}`;
};
