/* Regression tests for the 2026-10-02 queue hang.
 *
 * The bug: addMessage built the approval group with
 * total = commands.length, but non-command skills (attach) never
 * increment group.completed.  A group whose total counted an attach
 * could never resolve, so activeCommandGroup.resolved stayed false and
 * the Auto-Allow queue never drained.
 *
 * These tests assert the rule that prevents it: the group total counts
 * ONLY command skills.
 */
const assert = require('assert');
const { splitSkills } = require('../src/web/static/skill_split.js');

let pass = 0, fail = 0;
function t(name, fn) {
    try { fn(); console.log('  ok   ' + name); pass++; }
    catch (e) { console.log('  FAIL ' + name + ' -> ' + e.message); fail++; }
}

console.log('skill_split:');

t('mixed command+attach -> group counts only the command', function () {
    const { commandSkills, otherSkills } = splitSkills([
        { skill: 'command', code: 'ls' },
        { skill: 'attach', code: '/tmp/a.png' },
    ]);
    assert.strictEqual(commandSkills.length, 1);
    assert.strictEqual(otherSkills.length, 1);
    // The group total is commandSkills.length, so it can complete.
});

t('legacy entries with no skill field count as commands', function () {
    const { commandSkills } = splitSkills([{ code: 'ls' }, { code: 'pwd' }]);
    assert.strictEqual(commandSkills.length, 2);
});

t('attach-only message -> zero commands -> no group (no hang)', function () {
    const { commandSkills, otherSkills } = splitSkills([
        { skill: 'attach', code: '/tmp/a.png' },
    ]);
    assert.strictEqual(commandSkills.length, 0);
    assert.strictEqual(otherSkills.length, 1);
});

t('empty / null input does not throw', function () {
    assert.strictEqual(splitSkills([]).commandSkills.length, 0);
    assert.strictEqual(splitSkills(null).commandSkills.length, 0);
});

t('kaggle is a non-command skill', function () {
    const { commandSkills, otherSkills } = splitSkills([
        { skill: 'kaggle', code: 'status' },
    ]);
    assert.strictEqual(commandSkills.length, 0);
    assert.strictEqual(otherSkills.length, 1);
});

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
