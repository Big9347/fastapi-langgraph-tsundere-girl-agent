const utf8Encoder = new TextEncoder();
const decoder = new TextDecoder();

async function simulate() {
    const chunks = [
        'data: {"content": "He"}\n\n',
        'data: {"content": "llo"}\n\n',
        'data: {"content": "\\n\\nWorld", "done": false}\n\n',
        'data: {"content": "!", "done": true, "affection_score": 5}\n\n'
    ];

    let buffer = '';
    let fullText = '';

    for (const chunk of chunks) {
        const value = utf8Encoder.encode(chunk);
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data: ')) continue;
            try {
                const parsed = JSON.parse(trimmed.slice(6));
                if (parsed.content) {
                    fullText += parsed.content;
                    console.log("Updated fullText:", JSON.stringify(fullText));
                }
                if (parsed.done) {
                    console.log("Done! Affection:", parsed.affection_score);
                }
            } catch (e) {
                console.error("Parse error on:", trimmed.slice(6));
            }
        }
    }
}

simulate();
