import 'dotenv/config';

// Real platform data-path functions, actions and reducer; fixture only the request context.
export {getValueByPath, setValueByPath, setValues} from 'real-registry-widgets';
export function useWidgetContext() { return (window as any).testContext; }
export type WidgetRootState = any;
