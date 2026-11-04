export namespace CommandIDs {
  export const open = 'jupyter-ai-manager:open';
  export const listExtensions = 'jupyter-ai-manager:list-extensions';
  export const installExtension = 'jupyter-ai-manager:install-extension';
  export const installACPClient = 'jupyter-ai-manager:install-acp-client';
}

/**
 * Pip package of the ACP client extension, required to use the ACP clients.
 */
export const ACP_CLIENT_PACKAGE = 'jupyter-ai-acp-client';
