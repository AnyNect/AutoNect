/* Pure helper: split a commands[] array into shell commands and other
 * skills.  Loaded by the browser (via index.html) and by node tests.
 *
 * WHY THIS EXISTS (2026-10-02 regression):
 *   addMessage built the approval group with total = commands.length.
 *   Non-command skills (attach, kaggle) never increment group.completed,
 *   so a group whose total counted them never reached completed === total
 *   -- the frontend stayed permanently busy and the Auto-Allow queue
 *   never drained.  A non-command skill must NEVER count toward the
 *   command-approval group's total.  This module is that rule, in one
 *   place, with a test.
 */
(function (root) {
    function splitSkills(commands) {
        var commandSkills = [];
        var otherSkills = [];
        (commands || []).forEach(function (c) {
            var skill = (c && c.skill) || 'command';
            if (skill === 'command') {
                commandSkills.push(c);
            } else {
                otherSkills.push(c);
            }
        });
        return { commandSkills: commandSkills, otherSkills: otherSkills };
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { splitSkills: splitSkills };
    } else {
        root.splitSkills = splitSkills;
    }
})(typeof window !== 'undefined' ? window : globalThis);
