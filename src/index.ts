import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import {
  Dialog,
  ICommandPalette,
  MainAreaWidget,
  showDialog,
  showErrorMessage
} from '@jupyterlab/apputils';
import { IMainMenu } from '@jupyterlab/mainmenu';
import { ServerConnection } from '@jupyterlab/services';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { ReadonlyPartialJSONObject } from '@lumino/coreutils';
import { Menu } from '@lumino/widgets';

import {
  IACPClient,
  IAIExtension,
  fetchACPClients,
  fetchAIExtensions,
  installACPClient,
  installExtension,
  loadExtensionHandlers
} from './api';
import { ACP_CLIENT_PACKAGE, CommandIDs } from './tokens';

export { CommandIDs } from './tokens';

const PLUGIN_ID = 'jupyter-ai-manager:plugin';

const plugin: JupyterFrontEndPlugin<void> = {
  id: PLUGIN_ID,
  optional: [ICommandPalette, IMainMenu, ITranslator],
  description: 'A JupyterLab extension to install AI packages',
  autoStart: true,
  activate: async (
    app: JupyterFrontEnd,
    commandsPalette: ICommandPalette | null,
    mainMenu: IMainMenu | null,
    translator_: ITranslator | null
  ) => {
    const {
      AIManager,
      ConfirmACPInstallWidget,
      ConfirmInstallWidget,
      InstallProgressWidget
    } = await import('./manager');

    const translator = translator_ ?? nullTranslator;
    const trans = translator.load('jupyter-ai');

    const content = new AIManager({ commands: app.commands, trans });
    const panel = new MainAreaWidget({ content });
    panel.title.label = trans.__('AI Extensions');
    panel.title.closable = true;
    panel.id = 'jupyter-ai-manager-panel';

    const serverSettings = ServerConnection.makeSettings();

    // Cache used by isEnabled; populated asynchronously after activate.
    let extensionsCache: IAIExtension[] | null = null;

    app.commands.addCommand(CommandIDs.open, {
      label: trans.__('Open AI Manager widget'),
      execute: () => {
        if (!panel.isAttached) {
          app.shell.add(panel, 'main');
        }
        app.shell.activateById(panel.id);
      },
      describedBy: {
        args: {
          type: 'object',
          properties: {}
        }
      }
    });

    app.commands.addCommand(CommandIDs.listExtensions, {
      label: trans.__('List AI Extensions'),
      caption: trans.__(
        'Fetch the curated list of AI extensions and their installation status'
      ),
      execute: (): Promise<IAIExtension[]> => {
        return fetchAIExtensions(serverSettings);
      },
      describedBy: {
        args: {
          type: 'object',
          properties: {}
        }
      }
    });

    app.commands.addCommand(CommandIDs.installExtension, {
      label: (args: ReadonlyPartialJSONObject): string => {
        const { pip_package, name } = args;
        const displayName = name ?? pip_package ?? '';
        return displayName
          ? trans.__('Install %1', displayName)
          : trans.__('Install AI Extension');
      },
      caption: trans.__('Install an AI extension from the curated list'),
      isEnabled: (args: ReadonlyPartialJSONObject): boolean => {
        const { pip_package } = args;
        if (!pip_package || !extensionsCache) {
          return false;
        }
        const ext = extensionsCache.find(e => e.pip_package === pip_package);
        return !!ext && !ext.installed;
      },
      execute: async (args: ReadonlyPartialJSONObject): Promise<void> => {
        const { pip_package } = args;

        if (!pip_package) {
          await showErrorMessage(
            trans.__('Installation Error'),
            trans.__('No extension specified. Provide a pip_package argument.')
          );
          return;
        }

        let extensions: IAIExtension[];
        try {
          extensions = await fetchAIExtensions(serverSettings);
        } catch (err) {
          await showErrorMessage(
            trans.__('Installation Error'),
            trans.__(
              'Failed to fetch the extension list: %1',
              err instanceof Error ? err.message : String(err)
            )
          );
          return;
        }

        const ext = extensions.find(e => e.pip_package === pip_package);
        if (!ext) {
          await showErrorMessage(
            trans.__('Installation Error'),
            trans.__(
              '"%1" is not in the curated list of approved AI extensions.',
              pip_package
            )
          );
          return;
        }

        if (ext.installed) {
          return;
        }

        const confirm = await showDialog({
          title: trans.__('Install %1', ext.name),
          body: new ConfirmInstallWidget(ext, trans),
          buttons: [
            Dialog.cancelButton(),
            Dialog.okButton({ label: trans.__('Install') })
          ]
        });
        if (!confirm.button.accept) {
          return;
        }

        const progressDialog = new Dialog({
          title: trans.__('Installing %1\u2026', ext.name),
          body: new InstallProgressWidget(ext.name, trans),
          buttons: [],
          hasClose: false
        });
        void progressDialog.launch();

        try {
          await installExtension(ext.pip_package, serverSettings);
          await loadExtensionHandlers(ext.import_name, serverSettings);
          progressDialog.dispose();
          if (extensionsCache) {
            extensionsCache = extensionsCache.map(e =>
              e.pip_package === ext.pip_package ? { ...e, installed: true } : e
            );
            app.commands.notifyCommandChanged(CommandIDs.installExtension);
          }
          window.location.reload();
        } catch (err) {
          progressDialog.dispose();
          const message = err instanceof Error ? err.message : String(err);
          console.error(
            `jupyter-ai-manager: failed to install ${pip_package}`,
            err
          );
          await showErrorMessage(
            trans.__('Installation Error'),
            trans.__('Failed to install "%1": %2', pip_package, message)
          );
        }
      },
      describedBy: {
        args: {
          type: 'object',
          properties: {
            pip_package: {
              type: 'string',
              title: trans.__('Pip package name')
            },
            name: {
              type: 'string',
              title: trans.__('Display name')
            }
          },
          required: ['pip_package']
        }
      }
    });

    app.commands.addCommand(CommandIDs.installACPClient, {
      label: (args: ReadonlyPartialJSONObject): string =>
        args.name
          ? trans.__('Install %1', args.name)
          : trans.__('Install ACP client'),
      caption: trans.__('Install an ACP client on the server'),
      execute: async (args: ReadonlyPartialJSONObject): Promise<boolean> => {
        const { name } = args;
        if (typeof name !== 'string') {
          await showErrorMessage(
            trans.__('Installation Error'),
            trans.__('No ACP client specified. Provide a name argument.')
          );
          return false;
        }

        let client: IACPClient | undefined;
        let acpExtension: IAIExtension | undefined;
        try {
          const [clients, extensions] = await Promise.all([
            fetchACPClients(serverSettings),
            fetchAIExtensions(serverSettings)
          ]);
          client = clients.find(c => c.name === name);
          acpExtension = extensions.find(
            e => e.pip_package === ACP_CLIENT_PACKAGE
          );
        } catch (err) {
          await showErrorMessage(
            trans.__('Installation Error'),
            trans.__(
              'Failed to fetch the ACP client list: %1',
              err instanceof Error ? err.message : String(err)
            )
          );
          return false;
        }
        if (!client || !client.installable) {
          await showErrorMessage(
            trans.__('Installation Error'),
            trans.__('"%1" cannot be installed from JupyterLab.', name)
          );
          return false;
        }
        // The ACP client extension is required to use the ACP clients.
        const missingExtension =
          acpExtension && !acpExtension.installed ? acpExtension : null;
        if (client.available && !missingExtension) {
          return true;
        }

        const confirm = await showDialog({
          title: trans.__('Install %1', client.name),
          body: new ConfirmACPInstallWidget(client, trans, missingExtension),
          buttons: [
            Dialog.cancelButton(),
            Dialog.okButton({ label: trans.__('Install') })
          ]
        });
        if (!confirm.button.accept) {
          return false;
        }

        const progressDialog = new Dialog({
          title: trans.__('Installing %1…', client.name),
          body: new InstallProgressWidget(client.name, trans),
          buttons: [],
          hasClose: false
        });
        void progressDialog.launch();

        try {
          if (missingExtension) {
            await installExtension(
              missingExtension.pip_package,
              serverSettings
            );
            await loadExtensionHandlers(
              missingExtension.import_name,
              serverSettings
            );
          }
          const available =
            client.available ||
            (await installACPClient(client.name, serverSettings));
          progressDialog.dispose();
          if (missingExtension) {
            // Reload to activate the frontend of the newly installed extension.
            window.location.reload();
            return available;
          }
          if (!available) {
            await showDialog({
              title: trans.__('%1 installed', client.name),
              body: trans.__(
                'The installation succeeded, but "%1" was not found on the server PATH. Restart the server to make it available.',
                client.executable
              ),
              buttons: [Dialog.okButton()]
            });
          }
          return available;
        } catch (err) {
          progressDialog.dispose();
          console.error(`jupyter-ai-manager: failed to install ${name}`, err);
          await showErrorMessage(
            trans.__('Installation Error'),
            err instanceof Error ? err.message : String(err)
          );
          return false;
        }
      },
      describedBy: {
        args: {
          type: 'object',
          properties: {
            name: {
              type: 'string',
              title: trans.__('ACP client name')
            }
          },
          required: ['name']
        }
      }
    });

    // Build the Settings > AI Extensions submenu and populate it once the
    // extension list has been fetched.
    const submenu = mainMenu ? new Menu({ commands: app.commands }) : null;

    fetchAIExtensions(serverSettings)
      .then(extensions => {
        extensionsCache = extensions;
        if (submenu && mainMenu) {
          submenu.addItem({ command: CommandIDs.open });
          submenu.addItem({ type: 'separator' });
          for (const ext of extensions) {
            submenu.addItem({
              command: CommandIDs.installExtension,
              args: { pip_package: ext.pip_package, name: ext.name }
            });
          }
          if (extensionsCache.length) {
            submenu.title.label = trans.__('AI Extensions');
            mainMenu.settingsMenu.addGroup([{ type: 'submenu', submenu }], 100);
          }
        }
        app.commands.notifyCommandChanged(CommandIDs.installExtension);
      })
      .catch(err => {
        console.error(
          'jupyter-ai-manager: failed to fetch extension list',
          err
        );
      });

    commandsPalette?.addItem({
      category: trans.__('jupyter AI'),
      command: CommandIDs.open
    });

    console.log('JupyterLab extension jupyter-ai-manager is activated!');
  }
};

export default plugin;
