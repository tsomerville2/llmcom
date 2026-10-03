// Ensure a shared room exists; concurrent creators converge on the same room.
export async function ensureChannel(client, name) {
  const existing = (await client.channels.list()).find(channel => channel.name === name);
  if (existing) return { record:existing, created:false };
  try {
    return { record:await client.channels.create({ name, topic:'Live collaboration between explicitly joined warmed chats.' }), created:true };
  } catch (error) {
    const concurrent = (await client.channels.list()).find(channel => channel.name === name);
    if (concurrent) return { record:concurrent, created:false };
    throw error;
  }
}
