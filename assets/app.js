import init, { predict, get_locations } from '../pkg/how_will_i_die.js';

const MIN_AGE = 0;
const MAX_AGE = 110;

function setControlsEnabled(enabled) {
  const ids = ['location', 'age', 'sex', 'submit'];
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = !enabled;
  });
}

function renderError(container, message) {
  container.replaceChildren();
  const p = document.createElement('p');
  p.className = 'result-error';
  p.textContent = message;
  container.appendChild(p);
  container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function renderResults(container, causes) {
  container.replaceChildren();

  const heading = document.createElement('h3');
  heading.textContent = 'Most likely causes of death, ranked';
  container.appendChild(heading);

  const list = document.createElement('ol');
  causes.forEach((cause) => {
    const item = document.createElement('li');
    item.textContent = cause;
    list.appendChild(item);
  });
  container.appendChild(list);

  container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function main() {
  const status = document.getElementById('status');
  const locationSelect = document.getElementById('location');
  const placeholder = locationSelect.querySelector('option');

  try {
    await init({});
  } catch (err) {
    console.error('Failed to load the mortality data module.', err);
    status.textContent =
      'Something went wrong loading the data. Please refresh the page to try again.';
    status.classList.add('result-error');
    return;
  }

  // Populate the location dropdown straight from the module (no caching:
  // get_locations() is instant once the module has loaded).
  const locations = get_locations();
  locations.forEach((location) => {
    const option = document.createElement('option');
    option.value = location;
    option.textContent = location;
    locationSelect.appendChild(option);
  });

  if (placeholder) placeholder.textContent = 'Select your location';

  setControlsEnabled(true);
  status.textContent = '';
  status.hidden = true;

  const form = document.getElementById('prediction-form');
  const result = document.getElementById('result');

  form.addEventListener('submit', (event) => {
    event.preventDefault();

    const location = document.getElementById('location').value;
    const sex = document.getElementById('sex').value;
    const rawAge = document.getElementById('age').value;
    const age = parseInt(rawAge, 10);

    if (!Number.isInteger(age) || age < MIN_AGE || age > MAX_AGE) {
      renderError(result, `Please enter an age between ${MIN_AGE} and ${MAX_AGE}.`);
      return;
    }

    let causes;
    try {
      causes = predict(location, age, sex);
    } catch (err) {
      console.error('Prediction failed.', err);
      renderError(result, 'Something went wrong running the numbers. Please try again.');
      return;
    }

    if (causes && causes.length > 0) {
      renderResults(result, causes);
    } else {
      renderError(
        result,
        'No data available for that combination. Try a different location, age, or sex.'
      );
    }
  });
}

main();
