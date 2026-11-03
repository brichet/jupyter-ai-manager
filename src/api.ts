import { URLExt } from '@jupyterlab/coreutils';
import { ServerConnection } from '@jupyterlab/services';

import { requestAPI } from './request';

export interface IACPClient {
  name: string;
  executable: string;
  description: string;
  docs_url: string;
  /**
   * Command providing the ACP executable, when a one-liner exists.
   */
  install_command?: string;
  available: boolean;
}

export interface IAIExtension {
  name: string;
  pip_package: string;
  import_name: string;
  description: string;
  homepage_url: string;
  installed: boolean;
}

interface IExtensionsResponse {
  extensions: IAIExtension[];
}

interface IACPClientsResponse {
  acp_clients: IACPClient[];
}

interface IActionReply {
  status: 'ok' | 'warning' | 'error' | null;
  message?: string;
  needs_restart: ('frontend' | 'kernel' | 'server')[];
}

/**
 * Fetch the curated list of AI extensions and their install status.
 */
export async function fetchAIExtensions(
  serverSettings: ServerConnection.ISettings
): Promise<IAIExtension[]> {
  try {
    const response = await requestAPI<IExtensionsResponse>(
      'extensions',
      serverSettings
    );
    return response.extensions;
  } catch (err) {
    if (err instanceof ServerConnection.ResponseError) {
      throw new Error(
        `Failed to fetch extensions (${err.response.status}): ${err.message}`
      );
    }
    throw new Error(
      `Failed to fetch extensions: ${err instanceof Error ? err.message : 'Unknown error'}`
    );
  }
}

/**
 * Fetch the list of ACP clients and their availability status.
 */
export async function fetchACPClients(
  serverSettings: ServerConnection.ISettings
): Promise<IACPClient[]> {
  try {
    const response = await requestAPI<IACPClientsResponse>(
      'acp-clients',
      serverSettings
    );
    return response.acp_clients;
  } catch (err) {
    if (err instanceof ServerConnection.ResponseError) {
      throw new Error(
        `Failed to fetch ACP clients (${err.response.status}): ${err.message}`
      );
    }
    throw new Error(
      `Failed to fetch ACP clients: ${err instanceof Error ? err.message : 'Unknown error'}`
    );
  }
}

/**
 * Install an extension via JupyterLab's built-in extension manager API.
 */
export async function installExtension(
  pipPackage: string,
  serverSettings: ServerConnection.ISettings
): Promise<void> {
  const url = URLExt.join(serverSettings.baseUrl, 'lab/api/extensions');

  let response: Response;
  try {
    response = await ServerConnection.makeRequest(
      url,
      {
        method: 'POST',
        body: JSON.stringify({ cmd: 'install', extension_name: pipPackage }),
        headers: { 'Content-Type': 'application/json' }
      },
      serverSettings
    );
  } catch (err) {
    throw new ServerConnection.NetworkError(err as Error);
  }

  let data: IActionReply = { status: null, needs_restart: [] };
  const text = await response.text();
  if (text.length > 0) {
    try {
      data = JSON.parse(text) as IActionReply;
    } catch {
      // non-JSON body; fall through to ok check
    }
  }

  if (!response.ok) {
    throw new ServerConnection.ResponseError(
      response,
      data.message ?? `Install request failed (${response.status})`
    );
  }

  if (data.status !== 'ok') {
    throw new Error(
      data.message ?? `Install failed with status: ${data.status}`
    );
  }
}

/**
 * Ask the server to dynamically import and register the server extension handlers
 * of a newly installed package — avoiding a server restart.
 */
export async function loadExtensionHandlers(
  importName: string,
  serverSettings: ServerConnection.ISettings
): Promise<void> {
  try {
    await requestAPI<{ status: string }>('load', serverSettings, {
      method: 'POST',
      body: JSON.stringify({ import_name: importName }),
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (err) {
    if (err instanceof ServerConnection.ResponseError) {
      throw new Error(
        `Failed to load extension handlers (${err.response.status}): ${err.message}`
      );
    }
    throw new Error(
      `Failed to load extension handlers: ${err instanceof Error ? err.message : 'Unknown error'}`
    );
  }
}
