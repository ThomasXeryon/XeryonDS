export async function apiRequest(
  method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH",
  url: string,
  body?: any
) {
  const options: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
  };

  if (body) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(url, options);

  // Log errors for debugging
  if (!response.ok) {
    console.error(`API request failed: ${method} ${url}`, {
      status: response.status,
      statusText: response.statusText
    });
  }

  return response;
}