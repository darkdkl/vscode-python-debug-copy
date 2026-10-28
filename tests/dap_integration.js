const { spawn } = require('child_process');
const net = require('net');
const path = require('path');
const assert = require('assert');
const { readHelperSources, serialize, shortError } = require('../out/serializer');
const { copyableName, variablePath } = require('../out/names');

const root = path.join(__dirname, '..');
const helper = readHelperSources(path.join(root, 'python_debug_copy'));
const port = 40000 + Math.floor(Math.random() * 20000);
const HEADER_SEPARATOR = '\r\n\r\n';
const CONNECT_TIMEOUT_MS = 15000;

class DapClient {
	constructor(socket) {
		this.socket = socket;
		this.nextSequence = 1;
		this.pendingRequests = new Map();
		this.eventWaiters = [];
		this.buffer = Buffer.alloc(0);
		socket.on('data', (chunk) => this.onData(chunk));
	}

	onData(chunk) {
		this.buffer = Buffer.concat([this.buffer, chunk]);
		for (;;) {
			const headerEnd = this.buffer.indexOf(HEADER_SEPARATOR);
			if (headerEnd < 0) return;
			const bodyLength = Number(/Content-Length: (\d+)/i.exec(this.buffer.slice(0, headerEnd).toString())[1]);
			const bodyStart = headerEnd + HEADER_SEPARATOR.length;
			if (this.buffer.length < bodyStart + bodyLength) return;
			const message = JSON.parse(this.buffer.slice(bodyStart, bodyStart + bodyLength).toString('utf8'));
			this.buffer = this.buffer.slice(bodyStart + bodyLength);
			if (message.type === 'response') {
				const pending = this.pendingRequests.get(message.request_seq);
				this.pendingRequests.delete(message.request_seq);
				message.success ? pending.resolve(message.body || {}) : pending.reject(new Error(message.message));
			} else if (message.type === 'event') {
				this.eventWaiters = this.eventWaiters.filter((waiter) =>
					waiter.event === message.event ? (waiter.resolve(message.body), false) : true);
			}
		}
	}

	request(command, args) {
		const sequence = this.nextSequence++;
		const body = Buffer.from(JSON.stringify({ seq: sequence, type: 'request', command, arguments: args }), 'utf8');
		this.socket.write(`Content-Length: ${body.length}${HEADER_SEPARATOR}`);
		this.socket.write(body);
		return new Promise((resolve, reject) => this.pendingRequests.set(sequence, { resolve, reject }));
	}

	event(event) {
		return new Promise((resolve) => this.eventWaiters.push({ event, resolve }));
	}
}

function connect() {
	return new Promise((resolve, reject) => {
		const startedAt = Date.now();
		const attempt = () => {
			const socket = net.connect(port, '127.0.0.1');
			socket.once('connect', () => resolve(socket));
			socket.once('error', () =>
				Date.now() - startedAt > CONNECT_TIMEOUT_MS ? reject(new Error('connect timeout')) : setTimeout(attempt, 200));
		};
		attempt();
	});
}

async function main() {
	const env = { ...process.env };
	if (process.env.DEBUGPY_PYTHONPATH) env.PYTHONPATH = process.env.DEBUGPY_PYTHONPATH;
	const debuggee = spawn(process.env.PYTHON || 'python3', ['-m', 'debugpy', '--listen', `127.0.0.1:${port}`, '--wait-for-client',
		path.join(__dirname, 'fixtures', 'target.py')], { env, stdio: ['ignore', 'inherit', 'inherit'] });

	try {
		const dap = new DapClient(await connect());
		await dap.request('initialize', { adapterID: 'debugpy', clientID: 'test', linesStartAt1: true, columnsStartAt1: true });
		const initialized = dap.event('initialized');
		const stopped = dap.event('stopped');
		const attached = dap.request('attach', { justMyCode: false });
		await initialized;
		await dap.request('configurationDone', {});
		await attached;
		const { threadId } = await stopped;
		const { stackFrames } = await dap.request('stackTrace', { threadId, levels: 1 });
		const frameId = stackFrames[0].id;

		const evaluate = async (expression) =>
			String((await dap.request('evaluate', { expression, frameId, context: 'clipboard', format: { rawString: true } })).result);

		const nestedStartedAt = Date.now();
		const nested = JSON.parse(await serialize(evaluate, helper, 'nested', { mode: 'json', indent: 2 }));
		let node = nested;
		for (let level = 7; level >= 0; level--) {
			assert.strictEqual(node.level, level);
			node = node.items[0];
		}
		assert.deepStrictEqual(node, { leaf: true });
		console.log(`nested JSON      : OK, full 8 levels (${Date.now() - nestedStartedAt} ms)`);

		const bigStartedAt = Date.now();
		const bigText = await serialize(evaluate, helper, 'big', { mode: 'json', indent: 0 });
		const big = JSON.parse(bigText);
		assert.strictEqual(Object.keys(big).length, 2000);
		assert.strictEqual(big.k1999.payload.length, 200);
		console.log(`big JSON         : OK, ${bigText.length} chars, multi-chunk (${Date.now() - bigStartedAt} ms)`);

		const user = JSON.parse(await serialize(evaluate, helper, 'user', { mode: 'json' }));
		assert.deepStrictEqual(user, { name: 'Иван', created: '2024-05-01T12:00:00', roles: [{ id: 1, perms: ['read', 'write'] }] });
		console.log('dataclass JSON   :', JSON.stringify(user));

		const pythonText = await serialize(evaluate, helper, 'user.roles', { mode: 'python', pythonWidth: 100 });
		assert.match(pythonText, /^\[\{'id': 1, 'perms': \{'(read|write)', '(read|write)'\}\}\]$/);
		console.log('python dict      :', pythonText);

		const failure = async (expression) => {
			try {
				await serialize(evaluate, helper, expression, { mode: 'json' });
			} catch (error) {
				return shortError(error.message);
			}
			throw new Error(`${expression} did not fail`);
		};
		const nameError = await failure('no_such_var');
		assert.strictEqual(nameError, "NameError: name 'no_such_var' is not defined");
		const syntaxError = await failure('nested +');
		assert.match(syntaxError, /^SyntaxError: /);
		assert.ok(syntaxError.length < 100, syntaxError);
		console.log('errors           :', nameError, '|', syntaxError);

		const commented = JSON.parse(await serialize(evaluate, helper, 'user.roles  # note', { mode: 'json' }));
		assert.deepStrictEqual(commented[0].id, 1);
		console.log('trailing comment : OK');

		const [bigAtOnce, nameAtOnce] = await Promise.all([
			serialize(evaluate, helper, 'big', { mode: 'json', indent: 0 }),
			serialize(evaluate, helper, 'user.name', { mode: 'json' }),
		]);
		assert.strictEqual(Object.keys(JSON.parse(bigAtOnce)).length, 2000);
		assert.strictEqual(JSON.parse(nameAtOnce), 'Иван');
		console.log('two at once      : OK');

		assert.deepStrictEqual(JSON.parse(await serialize(evaluate, helper, 'error', { mode: 'json' })), { type: 'ValueError', args: ['boom', 42] });
		assert.strictEqual(await serialize(evaluate, helper, 'error', { mode: 'python' }), "ValueError('boom', 42)");
		console.log('exception        : OK');

		const { scopes } = await dap.request('scopes', { frameId });
		const locals = (await dap.request('variables', { variablesReference: scopes[0].variablesReference })).variables;
		const local = (name) => locals.find((variable) => variable.name === name);
		const keyNodes = (await dap.request('variables', { variablesReference: local('keys').variablesReference })).variables;
		const keyNames = keyNodes.map((variable) => variable.name)
			.filter((name) => !['special variables', 'function variables', 'len()'].includes(name));
		console.log('debugpy names    :', JSON.stringify(keyNames));
		assert.deepStrictEqual(keyNames.map(copyableName).sort(),
			['plain', "it's", 'say "hi"', 'tab\there', 'кириллица', '7', "('t', 1)"].sort());
		console.log('copy name        : OK');

		const child = async (parent, name) =>
			(await dap.request('variables', { variablesReference: parent.variablesReference })).variables.find((variable) => variable.name === name);
		const pathOf = (variable) => variablePath({ variable });
		const element = await child(local('catalog'), 'element');
		const elementInDict = await child(local('catalog_dict'), "'element'");
		const paths = [
			pathOf(await child(element, 'code')),
			pathOf(await child(await child(element, 'meta'), "'code'")),
			pathOf(await child(elementInDict, "'code'")),
			pathOf(await child(await child(elementInDict, "'tags'"), '1')),
			pathOf(keyNodes.find((variable) => variable.name === '7')),
			pathOf(keyNodes.find((variable) => variable.name === "('t', 1)")),
		];
		console.log('copy path        :', paths.join('  |  '));
		assert.deepStrictEqual(paths, [
			'catalog.element.code',
			"catalog.element.meta['code']",
			"catalog_dict['element']['code']",
			"catalog_dict['element']['tags'][1]",
			'keys[7]',
			"keys[('t', 1)]",
		]);
		assert.strictEqual(variablePath({ name: 'catalog.element' }), 'catalog.element');
		assert.strictEqual(variablePath({ variable: { name: 'special variables' } }), undefined);

		const odd = local('odd');
		const hasSpace = await child(odd, 'has space');
		const oddPaths = [
			variablePath({ container: odd, variable: hasSpace }),
			variablePath({ container: hasSpace, variable: await child(hasSpace, "'x'") }),
			variablePath({ container: odd, variable: await child(odd, 'class') }),
			variablePath({ container: odd, variable: await child(odd, "it's") }),
		];
		console.log('odd attributes   :', oddPaths.join('  |  '));
		assert.deepStrictEqual(oddPaths, [
			"getattr(odd, 'has space')",
			"getattr(odd, 'has space')['x']",
			"getattr(odd, 'class')",
			`getattr(odd, "it's")`,
		]);
		for (const [oddPath, expected] of [[oddPaths[1], '1'], [oddPaths[2], '2'], [oddPaths[3], '3']]) {
			assert.strictEqual(await evaluate(oddPath), expected);
		}

		const leftovers = await evaluate("[name for name in dir(__import__('builtins')) if 'python_debug_copy' in name]");
		assert.strictEqual(leftovers, '[]');
		const leftoverModules = await evaluate("[name for name in __import__('sys').modules if name.startswith('python_debug_copy')]");
		assert.strictEqual(leftoverModules, '[]');
		console.log('cleanup          : OK');

		await dap.request('disconnect', { terminateDebuggee: true }).catch(() => undefined);
		console.log('\nALL INTEGRATION CHECKS PASSED');
	} finally {
		setTimeout(() => debuggee.kill(), 500);
	}
}

main().catch((error) => {
	console.error(error);
	process.exit(1);
});
