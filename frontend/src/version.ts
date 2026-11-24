// Vite imports only this field, not the rest of package.json.
import { version } from '../package.json';

// npm needs 1.0.0-beta.1; the tag, Python and the sidebar spell it 1.0.0b1.
export const APP_VERSION = version.replace('-beta.', 'b');
