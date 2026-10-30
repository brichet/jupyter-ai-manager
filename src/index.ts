import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { ICommandPalette, MainAreaWidget } from '@jupyterlab/apputils';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';

const PLUGIN_ID = 'jupyter-ai-manager:plugin';

const plugin: JupyterFrontEndPlugin<void> = {
  id: PLUGIN_ID,
  optional: [ICommandPalette, ITranslator],
  description: 'A JupyterLab extension to install AI packages',
  autoStart: true,
  activate: async (
    app: JupyterFrontEnd,
    commandsPalette: ICommandPalette | null,
    translator_: ITranslator | null
  ) => {
    const { AIManager } = await import('./widget');

    const translator = translator_ ?? nullTranslator;
    const trans = translator.load('jupyter-ai');

    const content = new AIManager({ trans });
    const panel = new MainAreaWidget({ content });
    panel.title.label = trans.__('AI Extensions');
    panel.title.closable = true;
    panel.id = 'jupyter-ai-manager-panel';

    app.commands.addCommand('jupyter-ai-manager:open', {
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

    commandsPalette?.addItem({
      category: trans.__('jupyter AI'),
      command: 'jupyter-ai-manager:open'
    });

    console.log('JupyterLab extension jupyter-ai-manager is activated!');
  }
};

export default plugin;
