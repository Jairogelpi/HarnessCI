import { Composition } from "remotion";
import { TFMVideo } from "./Video";

export const RemotionRoot = () => {
  return (
    <Composition
      id="TFMVideo"
      component={TFMVideo}
      durationInFrames={10 * 30 * 30} // 10 slides × 30s × 30fps
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
