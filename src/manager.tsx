import React, { useState, useEffect } from 'react';

import { ReactWidget } from '@jupyterlab/apputils';
import { ServerConnection } from '@jupyterlab/services';
import { TranslationBundle } from '@jupyterlab/translation';
import { CommandRegistry } from '@lumino/commands';
import { Badge, Button, ProgressRing } from '@jupyter/react-components';

import { IAIExtension, fetchAIExtensions } from './api';
import { CommandIDs } from './tokens';

export class ConfirmInstallWidget extends ReactWidget {
  constructor(
    private readonly _ext: IAIExtension,
    private readonly _trans: TranslationBundle
  ) {
    super();
  }

  render(): JSX.Element {
    return (
      <div className="jp-jupyter-ai-manager-confirm">
        <p className="jp-jupyter-ai-manager-description">
          {this._ext.description}
        </p>
        <p className="jp-jupyter-ai-manager-warning">
          {this._trans.__(
            'The page will be reloaded automatically after installation.'
          )}
        </p>
      </div>
    );
  }
}

export class InstallProgressWidget extends ReactWidget {
  constructor(
    private readonly _name: string,
    private readonly _trans: TranslationBundle
  ) {
    super();
  }

  render(): JSX.Element {
    return (
      <div className="jp-jupyter-ai-manager-installing">
        <ProgressRing />
        <span>{this._trans.__('Installing %1\u2026', this._name)}</span>
      </div>
    );
  }
}

export interface IAIManagerOptions {
  commands: CommandRegistry;
  trans: TranslationBundle;
}

function AIManagerComponent({
  commands,
  trans
}: {
  commands: CommandRegistry;
  trans: TranslationBundle;
}): JSX.Element {
  const [extensions, setExtensions] = useState<IAIExtension[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const serverSettings = ServerConnection.makeSettings();
    fetchAIExtensions(serverSettings)
      .then(exts => setExtensions(exts))
      .catch(err => {
        setLoadError(
          err instanceof Error ? err.message : 'Failed to load extensions.'
        );
        console.error(
          'jupyter-ai-manager: failed to fetch extension list',
          err
        );
      });
  }, []);

  const handleInstall = (ext: IAIExtension): void => {
    void commands.execute(CommandIDs.installExtension, {
      pip_package: ext.pip_package,
      name: ext.name
    });
  };

  if (loadError) {
    return (
      <div className="jp-jupyter-ai-manager-container">
        <p className="jp-jupyter-ai-manager-error">{loadError}</p>
      </div>
    );
  }

  if (extensions === null) {
    return (
      <div className="jp-jupyter-ai-manager-container">
        <ProgressRing />
      </div>
    );
  }

  return (
    <div className="jp-jupyter-ai-manager-container">
      <h2 className="jp-jupyter-ai-manager-header">
        {trans.__('AI Extensions')}
      </h2>
      {extensions.length === 0 ? (
        <p className="jp-jupyter-ai-manager-empty">
          {trans.__('No AI extensions available.')}
        </p>
      ) : (
        <ul className="jp-jupyter-ai-manager-list">
          {extensions.map(ext => (
            <li key={ext.pip_package} className="jp-jupyter-ai-manager-item">
              <div className="jp-jupyter-ai-manager-info">
                <span className="jp-jupyter-ai-manager-name">{ext.name}</span>
                <p className="jp-jupyter-ai-manager-description">
                  {ext.description}
                </p>
              </div>
              {ext.installed ? (
                <Badge>{trans.__('Installed')}</Badge>
              ) : (
                <Button appearance="accent" onClick={() => handleInstall(ext)}>
                  {trans.__('Install')}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export class AIManager extends ReactWidget {
  constructor(options: IAIManagerOptions) {
    super();
    this._commands = options.commands;
    this._trans = options.trans;
    this.addClass('jp-jupyter-ai-manager-Widget');
  }

  render(): JSX.Element {
    return <AIManagerComponent commands={this._commands} trans={this._trans} />;
  }

  private _commands: CommandRegistry;
  private _trans: TranslationBundle;
}
