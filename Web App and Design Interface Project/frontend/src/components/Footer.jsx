import { NavLink } from "react-router-dom";
import Newsletter from "./Newsletter";
import "./Footer.css";

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="site-footer__grid container">
        <div className="site-footer__about">
          <div className="site-footer__brand">Café Fausse</div>
          1234 Culinary Ave, Suite 100
          <br />
          Napa Valley, CA 94558
          <br />
          (555) 867-5309
          <br />
          Tue–Sun · 5:00–10:00 PM
        </div>

        <div className="site-footer__col">
          <div className="site-footer__heading">Explore</div>
          <NavLink to="/">Home</NavLink>
          <NavLink to="/menu">Menu</NavLink>
          <NavLink to="/reservations">Reservations</NavLink>
          <NavLink to="/about">About Us</NavLink>
          <NavLink to="/gallery">Gallery</NavLink>
        </div>

        <div className="site-footer__col">
          <div className="site-footer__heading">Newsletter</div>
          <Newsletter compact />
        </div>

        <div className="site-footer__col">
          <div className="site-footer__heading">Follow</div>
          <div className="site-footer__social">
            <span>IG</span>
            <span>FB</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
