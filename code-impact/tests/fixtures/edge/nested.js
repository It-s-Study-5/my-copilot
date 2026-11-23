export function outer(value) {
  function inner(input) {
    return input + 1;
  }
  return inner(value);
}
