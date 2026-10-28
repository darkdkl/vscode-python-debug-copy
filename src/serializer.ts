import { randomBytes } from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { copyableName } from './names';

export type Mode = 'json' | 'python';

export type Evaluate = (expression: string) => Promise<string>;

export interface HelperSources {
	loader: string;
	modules: [string, string][];
}

const CHUNK_SIZE = 60000;
const MAX_ERROR_LENGTH = 300;
const HELPER_PACKAGE = 'python_debug_copy';
const HELPER_MODULE = `${HELPER_PACKAGE}.helper`;
const LOADER_FILE = 'loader.py';
const MODULE_FILES: [string, string][] = [
	[HELPER_PACKAGE, '__init__.py'],
	[`${HELPER_PACKAGE}.constants`, 'constants.py'],
	[HELPER_MODULE, 'helper.py'],
];

export function readHelperSources(packageDirectory: string): HelperSources {
	const read = (file: string) => fs.readFileSync(path.join(packageDirectory, file), 'utf8');
	return {
		loader: read(LOADER_FILE),
		modules: MODULE_FILES.map(([moduleName, file]) => [moduleName, read(file)]),
	};
}

export async function serialize(
	evaluateRaw: Evaluate,
	helper: HelperSources,
	expression: string,
	options: Record<string, unknown>,
): Promise<string> {
	const evaluate = async (pythonExpression: string) => unquote(await evaluateRaw(pythonExpression));
	const storageKey = `__python_debug_copy_${randomBytes(8).toString('hex')}__`;

	const optionsLiteral = JSON.stringify(JSON.stringify(options));
	const call =
		`(lambda pdc_namespace, pdc_value: (exec(${JSON.stringify(helper.loader)}, pdc_namespace), ` +
		`pdc_namespace['load_modules'](${JSON.stringify(helper.modules)})['${HELPER_MODULE}']` +
		`.run(pdc_value, ${optionsLiteral}, '${storageKey}'))[1])({}, (\n${expression}\n))`;

	const lengthText = await evaluate(call);
	const payloadLength = Number.parseInt(lengthText, 10);
	if (!Number.isFinite(payloadLength) || String(payloadLength) !== lengthText) {
		throw new Error(lengthText || 'unexpected empty result');
	}

	const payloadReference = `__import__('builtins').${storageKey}`;
	try {
		let payload = '';
		for (let start = 0; start < payloadLength; start += CHUNK_SIZE) {
			const chunk = await evaluate(`${payloadReference}[${start}:${start + CHUNK_SIZE}]`);
			payload += chunk.replace(/[^A-Za-z0-9+/=]/g, '');
		}
		if (payload.length !== payloadLength) {
			throw new Error(`payload size mismatch (${payload.length} != ${payloadLength})`);
		}
		return Buffer.from(payload, 'base64').toString('utf8');
	} finally {
		evaluate(`__import__('builtins').__dict__.pop('${storageKey}', None)`).catch(() => undefined);
	}
}

export function shortError(message: string): string {
	const lines = message.split('\n').map((line) => line.trim()).filter(Boolean);
	let text = lines[lines.length - 1] ?? message;
	const exceptionRepr = /^([A-Za-z_][\w.]*)\((['"])((?:\\.|(?!\2).)*)\2/s.exec(text);
	if (exceptionRepr) {
		const [, exceptionName, quote, quotedMessage] = exceptionRepr;
		text = `${exceptionName}: ${copyableName(quote + quotedMessage + quote)}`;
	}
	return text.length > MAX_ERROR_LENGTH ? `${text.slice(0, MAX_ERROR_LENGTH - 1)}…` : text;
}

function unquote(result: string): string {
	const trimmed = result.trim();
	const quote = trimmed[0];
	if (trimmed.length >= 2 && (quote === "'" || quote === '"') && trimmed[trimmed.length - 1] === quote) {
		return trimmed.slice(1, -1);
	}
	return trimmed;
}
