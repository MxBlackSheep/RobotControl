/**
 * Normalize multiline strings so they render correctly in the UI.
 * Converts Windows line endings and escaped newline sequences into real newlines.
 */
export const normalizeMultilineText = (value: string): string => {
  if (!value) {
    return value;
  }

  return value
    .replace(/\r\n/g, '\n') // collapse CRLF to LF
    .replace(/\\n/g, '\n'); // turn escaped newlines into actual newlines
};
