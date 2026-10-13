// Misma política que el backend: 10+ caracteres, mayúscula, minúscula y número.
export const isStrongPassword = p =>
  p.length >= 10 && /[a-z]/.test(p) && /[A-Z]/.test(p) && /\d/.test(p)