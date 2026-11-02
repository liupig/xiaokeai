import brand from '../public/branding/brand.json';

export type LogoVariant = keyof typeof brand.logos;
export const defaultLogo = brand.defaultLogo as LogoVariant;
export const logoVariants = brand.logos;

/** All product logos use this entry point; change brand.json to switch the default. */
export function getLogoUrl(variant: LogoVariant = defaultLogo): string {
  return `${import.meta.env.BASE_URL}branding/${brand.logos[variant].file}`;
}
