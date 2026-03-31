((LitElement) => {
	const html = LitElement.prototype.html;
	const css = LitElement.prototype.css;
	const version = '1.0.13-custom';

	const SUPPORTED_ENTITY_DOMAINS = [
		'input_text',
		'text',
		'var', 		// custom component: https://github.com/snarky-snark/home-assistant-variables/
	];
	const HA_ATTRIBUTE_MAX_LENGTH = 65535;
	const HA_STATE_MAX_LENGTH = 255;

	class LovelaceMultilineTextInput extends LitElement {

		static get properties() {
			return {
				_hass: {},
				stateObj: {},
				config: {},
			};
		}

		static get styles() {
			return css`
				.action-result-message-container {
					background-color: var(--primary-background-color);
					border: 1px solid var(--primary-color);
					border-radius: 3px;
					bottom: 10px;
					opacity: 1;
					padding: 5px;
					position: absolute;
					transition: opacity 0.5s linear;
				}
				.button {
					cursor: pointer;
					opacity: 1;
					padding: 5px 0;
					transition: opacity 0.5s linear;
				}
				.button-disabled {
					cursor: auto;
					pointer-events: none;
				}
				.flex-1 {
					flex: 1;
				}
				.flex-center {
					align-items: center;
					display: flex;
					justify-content: space-evenly;
				}
				.flex-col {
					display: flex;
					flex-direction: column;
				}
				.mti-content {
					display: flex;
					flex-direction: column;
					padding: 0;
					margin: 0;
				}
				.flex-left {
					display: flex;
					justify-content: start;
				}
				.flex-right {
					display: flex;
					justify-content: end;
				}
				.flex-row {
					display: flex;
					flex-direction: row;
				}
				.h-full {
					height: 100%;
				}
				.invisible {
					visibility: hidden;
				}
				.opacity-0 {
					opacity: 0 !important;
				}
				.space-between {
					justify-content: space-between;
				}
				.textarea {
					background: inherit;
					border: none;
					box-shadow: none;
					color: inherit;
					field-sizing: none;
					font: inherit;
					font-size: inherit;
					letter-spacing: inherit;
					line-height: inherit;
					max-width: 100%;
					min-width: 100%;
					outline: none;
					padding: inherit;
					resize: none;
					overflow: hidden;
					white-space: nowrap;
					word-spacing: inherit;
					word-wrap: break-word;
				}
				.textarea::placeholder {
					color: inherit;
					opacity: 0.2;
				}
				.text-bold {
					font-weight: bold;
				}
				.text-center {
					text-align: center;
				}
				.text-italic {
					font-style: italic; 
				}
				.text-red {
					color: red;
				}
				.text-small {
					font-size: 11px;
				}
				.w-full {
					width: 100%;
				}
				ha-card, ha-card * {
					box-sizing: border-box;
				}
			`;
		}

		updated() {
			this.updateComplete.then(() => {
				const new_state = this.getState();
				// only overwrite if state has changed since last overwrite
				if (this.config.last_updated_text === null || new_state !== this.config.last_updated_text) {
					this.setText(new_state, true);
				}
			});
		}

		render() {
			const cardStyle = [
				this.config.card_background != null ? `--ha-card-background: ${this.config.card_background}` : '',
				this.config.card_border === false ? '--ha-card-border-width: 0; --ha-card-box-shadow: none' : '',
			].filter(Boolean).join('; ');
			const inputStyle = [
				this.config.font_size != null ? `font-size: ${this.config.font_size}em` : '',
				this.config.color != null ? `color: ${this.config.color}` : '',
				this.config.input_height != null ? `height: ${this.config.input_height}; min-height: ${this.config.input_height}` : '',
				this.config.line_height != null ? `line-height: ${this.config.line_height}` : '',
				this.config.padding != null ? `padding: ${this.config.padding}` : '',
				this.config.padding_top_bottom != null ? `padding-top: ${this.config.padding_top_bottom}; padding-bottom: ${this.config.padding_top_bottom}` : '',
				this.config.padding_left_right != null ? `padding-left: ${this.config.padding_left_right}; padding-right: ${this.config.padding_left_right}` : '',
			].filter(Boolean).join('; ');
			return this.stateObj ?
				html`
					<ha-card .hass="${this._hass}" .config="${this.config}" class="flex-col" style="${cardStyle}">
						${this.config.title?.length ?
							html`<div class="card-header">${this.config.title}</div>`
							: ''
						}
						<div class="mti-content">
							<input
								class="textarea w-full"
								style="${inputStyle}"
								maxlength="${this.config.max_length !== -1 ? this.config.max_length : ''}"
								placeholder="${this.config.placeholder_text}"
								.value="${this.getState()}"
								@keydown="${(ev) => this.onTextareaKeydown(ev)}"
								@change="${() => this.onTextareaChanged()}"
								@input="${() => this.onTextareaChanged()}"
							/>
							${(this.config.show_buttons || this.config.display_action_results) ? html`
								<div class="card-buttons flex-center w-full">
									<div class="action-result-message-container text-small opacity-0 invisible"></div>
									${this.config.show_buttons ? Object.keys(this.config.buttons_ordered).map(this.renderButton.bind(this)) : null}
								</div>
							` : ''}
						</div>
					</ha-card>`
					: null;
		}

		getCardSize() {
			return Math.round(this.scrollHeight / 50);
		}

		renderButton(key) {
			return this.config.buttons[key] ?
				html`<div
						class="button button-${key}"
						title="${this.config.hints[key]}"
						@click="${() => { if (this.callAction(key) !== false) { this.callService(key); } }}"
						@tap="${() => { if (this.callAction(key) !== false) { this.callService(key); } }}"
					>
						<ha-icon icon="${this.config.icons[key]}"></ha-icon>
					</div>`
					: null;
		}

		getState() {
			let value = String(this.stateObj ? this.stateObj.state : this.config.initial_value);
			if(this.config.store_as.includes('attribute') && this.config.store_as_attribute_name?.length) {
				value = this.stateObj.attributes[this.config.store_as_attribute_name] || this.config.initial_value;
			}
			return String(value);
		}

		getText() {
			return this.shadowRoot ? this.shadowRoot.querySelector('.textarea')?.value : '';
		}

		setText(val, entity_update = false) {
			if (!this.shadowRoot) {
				return false;
			}

			this.shadowRoot.querySelector('.textarea').value = val;

			if (entity_update === true) {
				this.config.last_updated_text = val;
				this.resizeTextarea();
				this.updateCharactersInfoText();
			}
			else {
				this.onTextareaChanged();
			}
		}

		clearText() {
			clearTimeout(this.timeouts['autosave']);
			this.setText('');
		}

		pasteText() {
			clearTimeout(this.timeouts.autosave);

			const elem = this.shadowRoot.querySelector('.textarea');
			if (!elem) {
				return;
			}
			elem.focus();

			if(!navigator.clipboard) {
				console.warn('Sorry, your browser does not support the clipboard API.');
				return;
			}

			navigator.permissions.query({name: 'clipboard-read'}).then((status) => {
				if (status.state === 'granted' || status.state === 'prompt') {	
					navigator.clipboard.readText()
						.then((text) => {
							this.setText((elem.value ?? '') + text);
						})
						.catch((err) => {
							console.error('Error on paste: ', err);
						});
				} else {
					console.warn('Clipboard read permission denied!');
				}
			});
		}

		onTextareaChanged() {
			if (this.config.autosave) {
				clearTimeout(this.timeouts.autosave);
				this.timeouts.autosave = setTimeout(() => {
					if (this.callAction('save') !== false) {
						this.callService('save');
					}
				}, this.config.autosave_delay);
			}
			this.updateCharactersInfoText();
			this.resizeTextarea();
		}

		onTextareaKeydown(ev) {
			if (!ev || ev.key !== 'Enter' || ev.shiftKey) {
				return;
			}
			ev.preventDefault();
			if (this.callAction('save') !== false) {
				this.callService('save');
			}
		}

		updateCharactersInfoText() {
			if (!this.shadowRoot) {
				return;
			}

			const maxCharactersElem = this.shadowRoot.querySelector('span.info-characters-max');
			const minCharactersElem = this.shadowRoot.querySelector('span.info-characters-min');
			if (!maxCharactersElem && !minCharactersElem) {
				return;
			}

			const textLength = this.shadowRoot.querySelector('.textarea').value.length;
			const saveButton = this.shadowRoot.querySelector('div.button-save');
			let disableButton = false;

			const maxCharactersInfoText = `${textLength}/${this.config.max_length} max.`;
			if (maxCharactersElem) {
				maxCharactersElem.innerHTML = maxCharactersInfoText;
			}

			if (textLength >= this.config.max_length) {
				if (maxCharactersElem) {
					maxCharactersElem.classList.add('text-red');
				}
				disableButton = true;
			}
			else {
				if (maxCharactersElem) {
					maxCharactersElem.classList.remove('text-red');
				}
			}
			if (textLength <= this.config.max_length) {
				disableButton = false;
			}

			if (this.config.min_length > 0) {
				const minCharactersInfoText = `${textLength}/${this.config.min_length} min.`;
				if (minCharactersElem) {
					minCharactersElem.innerHTML = minCharactersInfoText;
				}

				if (textLength < this.config.min_length) {
					if (minCharactersElem) {
						minCharactersElem.classList.remove('invisible');
					}
					disableButton = true;
				}
				else {
					if (minCharactersElem) {
						minCharactersElem.classList.add('invisible');
					}
				}
			}

			if (saveButton) {
				if (disableButton) {
					saveButton.classList.add('button-disabled');
					saveButton.classList.add('text-red');
				}
				else {
					saveButton.classList.remove('button-disabled');
					saveButton.classList.remove('text-red');
				}
			}
		}

		resizeTextarea() {
			if (!this.shadowRoot) {
				return false;
			}
			const textArea = this.shadowRoot.querySelector('.textarea');
			if (!textArea) {
				return false;
			}
			textArea.style.minHeight = this.config.input_height || '0';
		}

		callAction(action) {
			if (typeof this.config.actions[action] === 'function') {
				return this.config.actions[action]();
			}
		}

		callService(service) {
			if (this.config.entity_domain === 'input_text' || this.config.entity_domain === 'text' || this.config.entity_domain === 'var') {
				const value = String((typeof this.config.service_values[service] === 'function' ? this.config.service_values[service]() : this.config.service_values[service]));
				if (this.config.service[service]) {
					const saveToStatePromise = () => {
						return this._hass.callService(this.config.entity_domain, this.config.service[service], { entity_id: this.stateObj.entity_id, value });
					};
					const saveToAttributePromise = () => {
						const setAttributes = {};
						setAttributes[this.config.store_as_attribute_name] = value;

						return this._hass.callService(this.config.entity_domain, this.config.service[service], { entity_id: this.stateObj.entity_id, attributes: setAttributes });
					};
					
					Promise.resolve()
						.then(this.config.store_as.includes('state') && saveToStatePromise)
						.then(this.config.store_as.includes('attribute') && this.config.entity_domain === 'var' && saveToAttributePromise)
						.then(() => {
							this.displayResultMessage(service, true);
						})
						.catch((error) => {
							this.displayResultMessage(service, false);
						});
				}
			}
		}

		displayResultMessage(service, success) {
			if (!this.config.display_action_results || !this.shadowRoot || !service || service.length < 1) {
				return;
			}

			const actionResultMessageContainer = this.shadowRoot.querySelector('div.action-result-message-container');
			if (!actionResultMessageContainer) {
				return;
			}

			let message = '';
			if (service === 'save') {
				message = success ? 'Content saved.' : 'An error occurred in the backend while saving!';
			}

			if (message.length) {
				actionResultMessageContainer.innerHTML = message;
				actionResultMessageContainer.classList.remove('invisible');
				actionResultMessageContainer.classList.remove('opacity-0');
				const buttons = this.shadowRoot.querySelectorAll('.button');
				buttons.forEach(elem => elem.classList.add('opacity-0'));

				setTimeout(function () {
					actionResultMessageContainer.classList.add('opacity-0');
					buttons.forEach(elem => elem.classList.remove('opacity-0'));
				}, 1500);
				setTimeout(function () {
					actionResultMessageContainer.classList.add('invisible');
					actionResultMessageContainer.innerHTML = '';
				}, 2000);
			}
		}

		actionSave() {
			const len = this.getText().length;
			return len >= this.config.min_length && (this.config.max_length === false || len <= this.config.max_length);
		}

		actionClear() {
			this.clearText();
			if (this.config.save_on_clear && this.callAction('save') !== false) {
				this.callService('save');
			}
		}

		actionPaste() {
			this.pasteText();
		}

		setConfig(config) {
			const normalizeCssSize = (value) => {
				if (value === undefined || value === null || value === '') {
					return null;
				}
				if (typeof value === 'number') {
					return `${value}px`;
				}
				return String(value);
			};

			const actions = {
				save: () => { return this.actionSave(); },
				paste: () => { return this.actionPaste(); },
				clear: () => { return this.actionClear(); },
			};

			// paste has no service, clear will be persisted by saving
			const services = {
				'input_text': {
					save: 'set_value',
				},
				'text': {
					save: 'set_value',
				},
				'var': {
					save: 'set',
				},
			};

			const serviceValues = {
				save: () => { return this.getText(); },
				paste: null,
				clear: '',
			};

			const buttons = {
				save: 1,
				paste: 2,
				clear: 3,
			};

			const icons = {
				save: 'mdi:content-save-outline',
				paste: 'mdi:content-paste',
				clear: 'mdi:trash-can-outline',
			};

			const hints = {
				save: 'Save',
				paste: 'Paste from clipboard',
				clear: 'Clear text'
			};

			const entityDomain = config.entity?.split('.')[0];
			if (!config.entity || !SUPPORTED_ENTITY_DOMAINS.includes(entityDomain)) {
				throw new Error('Please define an entity of type: ' + SUPPORTED_ENTITY_DOMAINS.join(', '));
			}

			const storeAsConfig = config.store_as || [ (entityDomain === 'input_text' || entityDomain === 'text') ? 'state' : 'attribute' ];

			if((entityDomain === 'input_text' || entityDomain === 'text') && storeAsConfig.includes('attribute')) {
				throw new Error(`Domain ${entityDomain} cannot store as attribute. Please use an entity of the var component to achieve this.`);
			}
			const storeAsState = storeAsConfig.includes('state');
			const storeMaxLength = storeAsState ? HA_STATE_MAX_LENGTH : HA_ATTRIBUTE_MAX_LENGTH;
			const maxLengthConfig = parseInt(config.max_length) || storeMaxLength;
			if(maxLengthConfig > storeMaxLength) {
				throw new Error(`max_length ${maxLengthConfig} exceeds the limit (${storeMaxLength}) of the current store_as configuration (${storeAsConfig.join(', ')})`);
			}

			const autosaveDelay = parseInt(config.autosave_delay_seconds);

			this.config = {
				autosave: config.autosave === true,
				autosave_delay: (isNaN(autosaveDelay) ? 1 : autosaveDelay) * 1000,
				display_action_results: (config.display_action_results ?? config.show_success_messages) !== false,
				entity: config.entity,
				entity_domain: entityDomain,
				initial_value: config.initial_value || '',
				max_length: maxLengthConfig,
				min_length: parseInt(config.min_length) || 0,
				min_lines_displayed: parseInt(config.min_lines_displayed ?? 2),
				placeholder_text: config.placeholder_text || '',
				save_on_clear: config.save_on_clear === true,
				store_as: storeAsConfig,
				store_as_attribute_name: config.store_as_attribute_name || 'multiline_text_input',
				title: config.title,

				show_buttons: config.buttons !== false,

				font_size: config.font_size != null ? parseFloat(config.font_size) : null,
				color: config.color != null ? String(config.color) : null,
				card_border: config.card_border !== undefined ? config.card_border : null,
				card_background: config.card_background != null ? String(config.card_background) : null,
				input_height: normalizeCssSize(config.input_height),
				line_height: normalizeCssSize(config.line_height),
				padding: normalizeCssSize(config.padding),
				padding_left_right: normalizeCssSize(config.padding_left_right),
				padding_top_bottom: normalizeCssSize(config.padding_top_bottom),

				actions: Object.assign({}, actions),
				buttons: Object.assign({}, buttons, config.buttons),
				buttons_ordered: {},
				hints: Object.assign({}, hints),
				icons: Object.assign({}, icons, config.icons),
				service: Object.assign({}, services[entityDomain]),
				service_values: Object.assign({}, serviceValues),
			};

			// filter out invalid values and buttons not to be displayed
			let stateButtons = Object.fromEntries(Object.entries(this.config.buttons).filter(([key, value]) => value === true || (!isNaN(value) && value !== 0)));
			// get ordered button keys
			stateButtons = Object.keys(stateButtons).sort(function (a, b) { return stateButtons[a] - stateButtons[b]; });
			// rebuild object with key => value
			stateButtons.forEach(key => this.config.buttons_ordered[key] = this.config.buttons[key]);

			this.config.min_length = Math.max(this.config.min_length, 0);

			if (this.config.max_length <= 0) {
				throw new Error('The max length should be greater than zero.');
			}
			if (this.config.min_length > this.config.max_length) {
				throw new Error('The min length must not be greater than max length.');
			}
			if (this.config.min_lines_displayed < 1) {
				throw new Error('At least one line must be displayed.');
			}
			if (this.config.autosave_delay < 0) {
				throw new Error('autosave_delay_seconds must be set to zero or a positive number (defaults to 1).');
			}
			
			this.timeouts = {
				autosave: null
			};
		}

		set hass(hass) {
			this._hass = hass;

			if (hass && this.config) {
				this.stateObj = this.config.entity in hass.states ? hass.states[this.config.entity] : null;
				if (this.stateObj) {
					if (this.config.title === undefined) {
						this.config.title = this.stateObj.attributes.friendly_name || '';
					}
					if (this.config.entity_domain === 'input_text' || this.config.entity_domain === 'text') {
						if (this.stateObj.attributes.mode !== 'text') {
							throw new Error(`The ${this.config.entity_domain} entity must be in 'text' mode (is: ${this.stateObj.attributes.mode})!`);
						}
					}
				}
				else {
					throw new Error(`Entity ${this.config.entity} does not exist!`);
				}
			}
		}
	}

	if (!customElements.get('lovelace-multiline-text-input-card')) {
		customElements.define('lovelace-multiline-text-input-card', LovelaceMultilineTextInput);
		console.info(
			`%c  multiline-text-input-card \n%c  version: ${version}    `,
			'color: orange; font-weight: bold; background: black',
			'color: white; font-weight: bold; background: dimgray',
		);
	}
})(window.LitElement || Object.getPrototypeOf(customElements.get('hui-masonry-view') || customElements.get('hui-view')));
