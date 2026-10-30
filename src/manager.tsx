import React, { useState, useEffect } from 'react';

import { ReactWidget } from '@jupyterlab/apputils';
import { ServerConnection } from '@jupyterlab/services';
import { TranslationBundle } from '@jupyterlab/translation';
import { Badge, Button, ProgressRing } from '@jupyter/react-components';

import {
  IAIExtension,
  fetchAIExtensions,
  installExtension,
  loadExtensionHandlers
} from './api';

export interface IAIManagerOptions {
  trans: TranslationBundle;
}

function AIManagerComponent({
  trans
}: {
  trans: TranslationBundle;
}): JSX.Element {
  const [extensions, setExtensions] = useState<IAIExtension[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [installing, setInstalling] = useState<Record<string, boolean>>({});
  const [installErrors, setInstallErrors] = useState<Record<string, string>>(
    {}
  );

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

  const handleInstall = async (ext: IAIExtension): Promise<void> => {
    const serverSettings = ServerConnection.makeSettings();
    setInstalling(prev => ({ ...prev, [ext.pip_package]: true }));
    setInstallErrors(prev => {
      const next = { ...prev };
      delete next[ext.pip_package];
      return next;
    });

    try {
      await installExtension(ext.pip_package, serverSettings);
      await loadExtensionHandlers(ext.import_name, serverSettings);
      window.location.reload();
    } catch (err) {
      setInstalling(prev => ({ ...prev, [ext.pip_package]: false }));
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error(`jupyter-ai-manager: failed to install ${ext.name}`, err);
      setInstallErrors(prev => ({
        ...prev,
        [ext.pip_package]: `Installation failed: ${message}`
      }));
    }
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
                <div className="jp-jupyter-ai-manager-actions">
                  <Button
                    appearance="accent"
                    disabled={installing[ext.pip_package] ?? false}
                    onClick={() => void handleInstall(ext)}
                  >
                    {installing[ext.pip_package] ? (
                      <>
                        <ProgressRing slot="start" />
                        {trans.__('Installing\u2026')}
                      </>
                    ) : (
                      trans.__('Install')
                    )}
                  </Button>
                  {installErrors[ext.pip_package] && (
                    <p className="jp-jupyter-ai-manager-error">
                      {installErrors[ext.pip_package]}
                    </p>
                  )}
                </div>
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
    this._trans = options.trans;
    this.addClass('jp-jupyter-ai-manager-Widget');
  }

  render(): JSX.Element {
    return <AIManagerComponent trans={this._trans} />;
  }

  private _trans: TranslationBundle;
}
