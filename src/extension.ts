import * as vscode from 'vscode';
import { copyableName, variablePath } from './names';
import { HelperSources, Mode, readHelperSources, serialize, shortError } from './serializer';

type Target = 'clipboard' | 'editor';

const PYTHON_DEBUG_TYPES = new Set(['debugpy', 'python']);

let helperSources: HelperSources;

export function activate(context: vscode.ExtensionContext) {
	helperSources = readHelperSources(context.asAbsolutePath('python_debug_copy'));

	const commands: [string, Mode, Target][] = [
		['pythonDebugCopy.copyAsJson', 'json', 'clipboard'],
		['pythonDebugCopy.copyAsPython', 'python', 'clipboard'],
		['pythonDebugCopy.openAsJson', 'json', 'editor'],
		['pythonDebugCopy.openAsPython', 'python', 'editor'],
	];
	context.subscriptions.push(
		vscode.commands.registerCommand('pythonDebugCopy.copyName', copyName),
		vscode.commands.registerCommand('pythonDebugCopy.copyPath', copyPath),
	);
	for (const [id, mode, target] of commands) {
		context.subscriptions.push(
			vscode.commands.registerCommand(id, (menuArgument?: unknown) => run(menuArgument, mode, target)),
		);
	}
}

export function deactivate() {}

async function copyPath(menuArgument?: unknown) {
	const path = variablePath(menuArgument);
	if (!path) {
		vscode.window.showWarningMessage('Python Debug Copy: this node has no path (synthetic node like "special variables").');
		return;
	}
	await vscode.env.clipboard.writeText(path);
	vscode.window.setStatusBarMessage(`$(check) Copied path: ${path}`, 3000);
}

async function copyName(menuArgument?: unknown) {
	const menuContext = (menuArgument && typeof menuArgument === 'object' ? menuArgument : {}) as Record<string, any>;
	const name = menuContext.variable?.name ?? menuContext.name;
	if (typeof name !== 'string' || !name) {
		vscode.window.showWarningMessage('Python Debug Copy: select a variable in the Variables or Watch view.');
		return;
	}
	const text = copyableName(name);
	await vscode.env.clipboard.writeText(text);
	vscode.window.setStatusBarMessage(`$(check) Copied name: ${text}`, 3000);
}

async function run(menuArgument: unknown, mode: Mode, target: Target) {
	const session = vscode.debug.activeStackItem?.session ?? vscode.debug.activeDebugSession;
	if (!session) {
		vscode.window.showWarningMessage('Python Debug Copy: no active debug session.');
		return;
	}
	if (!PYTHON_DEBUG_TYPES.has(session.type)) {
		vscode.window.showWarningMessage(`Python Debug Copy: session type "${session.type}" is not a Python (debugpy) session.`);
		return;
	}

	const expression = await resolveExpression(menuArgument);
	if (!expression) {
		return;
	}

	let text: string;
	try {
		text = await vscode.window.withProgress(
			{ location: vscode.ProgressLocation.Window, title: `Serializing ${expression}…` },
			async () => serialize(sessionEvaluator(session, await currentFrameId(session)), helperSources, expression, buildOptions(mode)),
		);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		vscode.window.showErrorMessage(`Python Debug Copy: failed to evaluate "${expression}": ${shortError(message)}`);
		return;
	}

	if (target === 'clipboard') {
		await vscode.env.clipboard.writeText(text);
		const label = mode === 'json' ? 'JSON' : 'Python';
		vscode.window.setStatusBarMessage(`$(check) Copied ${expression} as ${label} (${text.length.toLocaleString()} chars)`, 4000);
	} else {
		const document = await vscode.workspace.openTextDocument({ content: text, language: mode });
		await vscode.window.showTextDocument(document, { preview: false });
	}
}

async function resolveExpression(menuArgument: unknown): Promise<string | undefined> {
	const menuContext = (menuArgument && typeof menuArgument === 'object' ? menuArgument : {}) as Record<string, any>;

	if (menuContext.variable && typeof menuContext.variable === 'object') {
		const path = variablePath(menuContext);
		if (path) {
			return path;
		}
		vscode.window.showWarningMessage(
			`Python Debug Copy: "${menuContext.variable.name}" has no evaluatable expression (synthetic node like "special variables"). Select a real variable.`,
		);
		return undefined;
	}
	if (typeof menuContext.evaluateName === 'string' && menuContext.evaluateName) {
		return menuContext.evaluateName;
	}
	if (typeof menuContext.name === 'string' && menuContext.name) {
		return menuContext.name;
	}

	const editor = vscode.window.activeTextEditor;
	if (editor && !editor.selection.isEmpty) {
		const selected = editor.document.getText(editor.selection).trim();
		if (selected) {
			return selected;
		}
	}

	return vscode.window.showInputBox({
		prompt: 'Python expression to serialize (evaluated in the selected stack frame)',
		placeHolder: 'e.g. response.json() or self.__dict__',
	});
}

async function currentFrameId(session: vscode.DebugSession): Promise<number | undefined> {
	const stackItem = vscode.debug.activeStackItem;
	if (!stackItem || stackItem.session.id !== session.id) {
		return undefined;
	}
	if (stackItem instanceof vscode.DebugStackFrame) {
		return stackItem.frameId;
	}
	const trace = await session.customRequest('stackTrace', { threadId: stackItem.threadId, startFrame: 0, levels: 1 });
	return trace?.stackFrames?.[0]?.id;
}

function buildOptions(mode: Mode) {
	const config = vscode.workspace.getConfiguration('pythonDebugCopy');
	return {
		mode,
		indent: config.get<number>('json.indent', 2),
		ensureAscii: config.get<boolean>('json.ensureAscii', false),
		pythonWidth: config.get<number>('python.width', 100),
		sortKeys: config.get<boolean>('sortKeys', false),
		maxDepth: config.get<number>('maxDepth', 100),
		skipPrivateAttributes: config.get<boolean>('skipPrivateAttributes', false),
		includeTypeName: config.get<boolean>('includeTypeName', false),
		dataFrameOrient: config.get<string>('dataFrameOrient', 'records'),
	};
}

function sessionEvaluator(session: vscode.DebugSession, frameId: number | undefined) {
	return async (expression: string): Promise<string> => {
		const response = await session.customRequest('evaluate', {
			expression,
			frameId,
			context: 'clipboard',
			format: { rawString: true },
		});
		return String(response?.result ?? '');
	};
}
