import { ServerConnection } from '@jupyterlab/services';
import { TranslationBundle } from '@jupyterlab/translation';
import { Widget } from '@lumino/widgets';

import {
  IAIExtension,
  fetchAIExtensions,
  installExtension,
  loadExtensionHandlers
} from './api';

export interface IInstallerWidgetOptions {
  trans: TranslationBundle;
}

export class InstallerWidget extends Widget {
  constructor(options: IInstallerWidgetOptions) {
    super();
    this._trans = options.trans;
    this.addClass('jp-jupyter-ai-installer-Widget');
    void this._init();
  }

  private async _init(): Promise<void> {
    const serverSettings = ServerConnection.makeSettings();
    let extensions: IAIExtension[];

    try {
      extensions = await fetchAIExtensions(serverSettings);
    } catch (err) {
      this._renderError(
        err instanceof Error ? err.message : 'Failed to load extensions.'
      );
      console.error(
        'jupyter-ai-installer: failed to fetch extension list',
        err
      );
      return;
    }

    this._render(extensions);
  }

  private _render(extensions: IAIExtension[]): void {
    const container = document.createElement('div');
    container.className = 'jp-jupyter-ai-installer-container';

    const header = document.createElement('h2');
    header.className = 'jp-jupyter-ai-installer-header';
    header.textContent = this._trans.__('AI Extensions');
    container.appendChild(header);

    if (extensions.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'jp-jupyter-ai-installer-empty';
      empty.textContent = this._trans.__('No AI extensions available.');
      container.appendChild(empty);
    } else {
      const list = document.createElement('ul');
      list.className = 'jp-jupyter-ai-installer-list';
      for (const ext of extensions) {
        list.appendChild(this._renderItem(ext));
      }
      container.appendChild(list);
    }

    this.node.appendChild(container);
  }

  private _renderItem(ext: IAIExtension): HTMLLIElement {
    const item = document.createElement('li');
    item.className = 'jp-jupyter-ai-installer-item';

    const info = document.createElement('div');
    info.className = 'jp-jupyter-ai-installer-info';

    const name = document.createElement('span');
    name.className = 'jp-jupyter-ai-installer-name';
    name.textContent = ext.name;
    info.appendChild(name);

    const description = document.createElement('p');
    description.className = 'jp-jupyter-ai-installer-description';
    description.textContent = ext.description;
    info.appendChild(description);

    item.appendChild(info);

    if (ext.installed) {
      const badge = document.createElement('span');
      badge.className = 'jp-jupyter-ai-installer-badge';
      badge.textContent = this._trans.__('Installed');
      item.appendChild(badge);
    } else {
      const button = document.createElement('button');
      button.className =
        'jp-jupyter-ai-installer-btn jp-mod-styled jp-mod-accept';
      button.textContent = this._trans.__('Install');
      button.addEventListener(
        'click',
        () => void this._install(ext, item, button)
      );
      item.appendChild(button);
    }

    return item;
  }

  private _renderError(message: string): void {
    const error = document.createElement('p');
    error.className = 'jp-jupyter-ai-installer-error';
    error.textContent = message;
    this.node.appendChild(error);
  }

  private async _install(
    ext: IAIExtension,
    item: HTMLLIElement,
    button: HTMLButtonElement
  ): Promise<void> {
    button.disabled = true;
    button.textContent = this._trans.__('Installing…');

    const serverSettings = ServerConnection.makeSettings();

    try {
      await installExtension(ext.pip_package, serverSettings);

      button.textContent = this._trans.__('Loading…');
      await loadExtensionHandlers(ext.import_name, serverSettings);

      window.location.reload();
    } catch (err) {
      button.disabled = false;
      button.textContent = this._trans.__('Install');
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error(`jupyter-ai-installer: failed to install ${ext.name}`, err);

      const errorEl = document.createElement('p');
      errorEl.className = 'jp-jupyter-ai-installer-error';
      errorEl.textContent = `Installation failed: ${message}`;
      item.appendChild(errorEl);
    }
  }

  private _trans: TranslationBundle;
}
