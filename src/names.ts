const PYTHON_STRING_ESCAPES: Record<string, string> = {
	'\\': '\\', "'": "'", '"': '"', n: '\n', t: '\t', r: '\r', a: '\x07', b: '\b', f: '\f', v: '\v', '0': '\0',
};

const PYTHON_CONTROL_ESCAPES: Record<string, string> = { '\n': '\\n', '\r': '\\r', '\t': '\\t' };

const PYTHON_KEYWORDS = new Set([
	'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def', 'del',
	'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal',
	'not', 'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield',
]);

export function copyableName(name: string): string {
	const quoted = /^(['"])(.*)\1$/s.exec(name);
	if (!quoted) {
		return name;
	}
	return quoted[2].replace(/\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|.)/gs, (sequence, escape: string) => {
		if (escape.length > 1) {
			return String.fromCodePoint(parseInt(escape.slice(1), 16));
		}
		return PYTHON_STRING_ESCAPES[escape] ?? sequence;
	});
}

export function variablePath(menuArgument: unknown): string | undefined {
	const context = (menuArgument && typeof menuArgument === 'object' ? menuArgument : {}) as Record<string, any>;
	if (context.variable && typeof context.variable === 'object') {
		const path = context.variable.evaluateName;
		if (typeof path !== 'string' || !path) {
			return undefined;
		}
		return withAttributeAccess(path, context.variable.name, context.container);
	}
	const path = context.evaluateName || context.name;
	return typeof path === 'string' && path ? path : undefined;
}

function withAttributeAccess(path: string, name: unknown, container: any): string {
	const parentPath = container?.evaluateName;
	if (typeof parentPath === 'string' && parentPath && path.startsWith(parentPath)) {
		path = getattrPath(parentPath, container.name) + path.slice(parentPath.length);
	}
	return getattrPath(path, name);
}

function getattrPath(path: string, name: unknown): string {
	if (typeof name !== 'string' || isIdentifier(name) || !path.endsWith(`.${name}`)) {
		return path;
	}
	return `getattr(${path.slice(0, -name.length - 1)}, ${pythonStringLiteral(name)})`;
}

function pythonStringLiteral(text: string): string {
	const quote = text.includes("'") && !text.includes('"') ? '"' : "'";
	const escaped = [...text].map((character) => {
		if (character === '\\' || character === quote) {
			return `\\${character}`;
		}
		const code = character.codePointAt(0)!;
		if (code < 0x20 || code === 0x7f) {
			return PYTHON_CONTROL_ESCAPES[character] ?? `\\x${code.toString(16).padStart(2, '0')}`;
		}
		return character;
	});
	return quote + escaped.join('') + quote;
}

function isIdentifier(name: string): boolean {
	return /^[\p{L}\p{Nl}_][\p{L}\p{Nl}\p{Mn}\p{Mc}\p{Nd}\p{Pc}]*$/u.test(name) && !PYTHON_KEYWORDS.has(name);
}
