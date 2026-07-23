import { useState } from "react";

export function QuickComposer({ onSend }: { onSend: (message: string) => void }) {
  const [message, setMessage] = useState("");

  return (
    <form
      className="quick-composer"
      onSubmit={(event) => {
        event.preventDefault();
        const trimmedMessage = message.trim();
        if (!trimmedMessage) return;
        onSend(trimmedMessage);
        setMessage("");
      }}
    >
      <label htmlFor="workspace-command">Workspace command</label>
      <input
        id="workspace-command"
        name="workspace-command"
        type="text"
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        placeholder="Describe the operation to prepare"
      />
      <button
        type="submit"
        disabled={!message.trim()}
      >
        Prepare operation
      </button>
    </form>
  );
}
